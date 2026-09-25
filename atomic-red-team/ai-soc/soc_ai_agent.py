"""
soc_ai_agent.py  —  통합 SOC AI Agent (L1 Triage + L2 Analysis + L3 Engineering)

한 프로세스에서:
  - 백그라운드 스레드: Wazuh 폴링 → L1 판정+요약 → (진탐) L2 분석 → 탐지공백이면
                       L2 스레드에 [Sigma 생성] 버튼 부착
  - 메인(Socket Mode): 버튼 이벤트 처리
      [Sigma 생성] → Gemini Sigma 생성 → Wazuh 적용/검증 → [운영반영][거부] 버튼
      [운영 반영] → IR 리포트 생성 + 반영 확정 (사람 승인2)
      [거부]      → 검증 룰 롤백

SOC 레벨:
  L1 = 빠른 선별(오탐/심각도/격차)   L2 = 심층분석+L3후보   L3 = Sigma 생성·검증·반영
  모든 파괴적 단계는 사람 버튼 승인(계획서 원칙).

전제:
  - Docker Wazuh(9200 + container docker exec)
  - Slack Bot Token + App Token(Socket Mode) + Interactivity ON
  - Gemini API Key (무료 gemini-flash-lite-latest)
  - py -m pip install slack-bolt requests pyyaml
  - 환경변수: SLACK_BOT_TOKEN, SLACK_APP_TOKEN, GEMINI_API_KEY
"""
import os
import re
import json
import time
import threading
import datetime
import subprocess
import urllib3
import requests
import yaml
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ── 설정 ──────────────────────────────────────────────
WAZUH_INDEXER = "https://localhost:9200"
WAZUH_USER = "admin"
WAZUH_PASS = "SecretPassword"
WAZUH_CONTAINER = "single-node-wazuh.manager-1"
LOCAL_RULES = "/var/ossec/etc/rules/local_rules.xml"
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-lite-latest")
GEMINI_URL = (f"https://generativelanguage.googleapis.com/v1beta/models/"
              f"{GEMINI_MODEL}:generateContent")
SLACK_CHANNEL = "#soc-alerts"
POLL_INTERVAL = 30
SEEN_FILE = "seen_alerts.txt"
MIN_LEVEL = 3
L3_RULE_ID = "100200"

KNOWN_FP = ["__PSScriptPolicyTest_", "\\CLR_v4.0\\UsageLogs\\",
            "\\SoftwareDistribution\\Download\\", "MsMpEng.exe"]
ART_ANCILLARY = {"T1059", "T1059.001", "T1059.003", "T1105",
                 "T1087", "T1574.001", "T1570"}
FIELD_MAP = {
    "Image": "win.eventdata.image", "CommandLine": "win.eventdata.commandLine",
    "ParentImage": "win.eventdata.parentImage",
    "ParentCommandLine": "win.eventdata.parentCommandLine",
    "TargetFilename": "win.eventdata.targetFilename",
    "TargetObject": "win.eventdata.targetObject",
    "Details": "win.eventdata.details", "User": "win.eventdata.user",
}

app = App(token=os.environ["SLACK_BOT_TOKEN"])
_pending = {}   # thread_ts → {sigma, technique, xml}


# ══ 공통: Gemini 호출 ═════════════════════════════════
def ask_gemini(prompt, max_tokens=400, timeout=60, retries=2):
    if not GEMINI_KEY:
        return "(GEMINI_API_KEY 미설정)"
    for attempt in range(retries + 1):
        try:
            r = requests.post(GEMINI_URL,
                headers={"Content-Type": "application/json", "x-goog-api-key": GEMINI_KEY},
                json={"contents": [{"parts": [{"text": prompt}]}],
                      "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.3}},
                timeout=timeout)
            if r.status_code == 429:
                return "(Gemini 한도 초과)"
            if r.status_code == 503 and attempt < retries:
                time.sleep(3); continue
            r.raise_for_status()
            return r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        except requests.exceptions.Timeout:
            return "(시간초과)"
        except Exception as e:
            if attempt < retries:
                time.sleep(3); continue
            return f"(실패: {e})"
    return "(재시도 초과)"


# ══ Wazuh 폴링 ════════════════════════════════════════
def poll_wazuh(since_min=5, after_ts=None):
    """얼럿 조회. after_ts(ISO)가 있으면 그 시각 이후만 (실행 시점 기준)."""
    if after_ts:
        gte = after_ts
    else:
        gte = (datetime.datetime.now(datetime.timezone.utc)
               - datetime.timedelta(minutes=since_min)).strftime("%Y-%m-%dT%H:%M:%S")
    q = {"size": 30, "sort": [{"timestamp": {"order": "desc"}}],
         "query": {"bool": {"must": [
             {"range": {"timestamp": {"gte": gte}}},
             {"range": {"rule.level": {"gte": MIN_LEVEL}}}]}}}
    r = requests.get(f"{WAZUH_INDEXER}/wazuh-alerts-*/_search",
                     auth=(WAZUH_USER, WAZUH_PASS), json=q, verify=False, timeout=30)
    r.raise_for_status()
    return r.json().get("hits", {}).get("hits", [])


# ══ L1 판정 ═══════════════════════════════════════════
def is_fp(src):
    return any(m in json.dumps(src, ensure_ascii=False) for m in KNOWN_FP)

def judge_verdict(fp, mitre_ids):
    if fp:
        return "오탐후보"
    ids = [i for i in mitre_ids if i]
    if ids and all(i in ART_ANCILLARY for i in ids):
        return "탐지공백"
    if ids:
        return "탐지됨"
    return "미분류"

def triage(alert):
    src = alert["_source"]; rule = src.get("rule", {})
    ed = src.get("data", {}).get("win", {}).get("eventdata", {})
    mitre = rule.get("mitre", {}); mids = mitre.get("id", [])
    fp = is_fp(src)
    return {
        "level": rule.get("level"), "desc": rule.get("description", ""),
        "mitre_id": ",".join(mids) or "-",
        "mitre_tech": ",".join(mitre.get("technique", [])) or "-",
        "image": ed.get("image", ""),
        "cmdline": (ed.get("commandLine") or ed.get("targetObject") or "")[:200],
        "agent": src.get("agent", {}).get("name", ""),
        "fp": fp, "verdict": judge_verdict(fp, mids),
        "primary_tech": (mids[0] if mids else "-"),
    }


# ══ L1/L2 Slack 게시 ══════════════════════════════════
def l1_prompt(c):
    return (f"SOC L1 분석가로서 아래 얼럿을 한국어 2~3문장 요약하고 위협 가능성"
            f"(높음/중간/낮음)을 판단하세요. 간결히.\n"
            f"- 룰: {c['desc']} (level {c['level']})\n- ATT&CK: {c['mitre_id']}\n"
            f"- 프로세스: {c['image']}\n- 명령: {c['cmdline']}\n"
            f"- 오탐필터: {'예' if c['fp'] else '아니오'}")

def l2_prompt(c):
    gap = "이 얼럿은 부수 로그만 잡히고 대상 기법은 미탐된 '탐지 공백'입니다. " if c["verdict"] == "탐지공백" else ""
    return (f"SOC L2 심층분석가로서 아래 위협을 개조식 분석. {gap}\n"
            f"1) 공격 맥락 2) 탐지 평가(격차 여부) 3) 권고(Sigma 방향)\n"
            f"- 기법: {c['mitre_id']} ({c['mitre_tech']})\n- 프로세스: {c['image']}\n"
            f"- 명령: {c['cmdline']}\n- 판정: {c['verdict']}")

def post_l1(c):
    emo = "🔴" if c["level"] >= 12 else ("🟠" if c["level"] >= 7 else "🟡")
    tag = {"오탐후보": " · ⚪오탐후보", "탐지공백": " · 🟣탐지공백",
           "탐지됨": " · 🟢탐지됨"}.get(c["verdict"], "")
    ai = ask_gemini(l1_prompt(c), 300)
    body = (f"{emo} *{c['mitre_id']}* (level {c['level']}){tag}\n"
            f"> {c['desc']}\n> 에이전트: {c['agent']} · 프로세스: `{c['image'].split(chr(92))[-1]}`\n"
            f"\n*L1 AI 분석:*\n{ai}")
    return app.client.chat_postMessage(channel=SLACK_CHANNEL, text=body, mrkdwn=True)["ts"]

def post_l2(c, thread_ts):
    ai = ask_gemini(l2_prompt(c), 400)
    app.client.chat_postMessage(channel=SLACK_CHANNEL, thread_ts=thread_ts,
                                text=f"*🔬 L2 심층 분석:*\n{ai}", mrkdwn=True)
    # 탐지공백이면 L3 [Sigma 생성] 버튼
    if c["verdict"] == "탐지공백":
        val = json.dumps({"tech": c["primary_tech"], "ctx": c["cmdline"][:150]})
        app.client.chat_postMessage(
            channel=SLACK_CHANNEL, thread_ts=thread_ts,
            text="🟣 탐지 공백 — L3 커스텀 Sigma 생성 대상",
            blocks=[
                {"type": "section", "text": {"type": "mrkdwn",
                 "text": "🟣 *탐지 공백* — L3 커스텀 Sigma 룰 생성 대상"}},
                {"type": "actions", "elements": [
                    {"type": "button", "text": {"type": "plain_text", "text": "⚙️ Sigma 생성"},
                     "style": "primary", "action_id": "gen_sigma", "value": val}]}])


# ══ L3: Sigma 변환·적용 ═══════════════════════════════
def _esc(v):
    P = "\x00"; t = v.replace("\\", P); t = re.escape(t); return t.replace(P, r"\\+")

def sigma_to_xml(sigma_yaml):
    try:
        rule = yaml.safe_load(sigma_yaml)
    except Exception as e:
        return None, f"YAML 파싱 실패: {e}"
    if not isinstance(rule, dict):
        return None, "YAML 구조 오류"
    det = rule.get("detection", {})
    fields = []
    for name, body in det.items():
        if name == "condition" or not isinstance(body, dict):
            continue
        for fe, val in body.items():
            f = fe.split("|")[0]; mods = fe.split("|")[1:]
            wf = FIELD_MAP.get(f)
            if not wf:
                continue
            vals = val if isinstance(val, list) else [val]
            rgxs = []
            for v in vals:
                e = _esc(str(v))
                rgxs.append(f"{e}$" if "endswith" in mods else e)
            if "all" in mods:
                for rg in rgxs: fields.append((wf, rg))
            else:
                fields.append((wf, "|".join(f"(?:{r})" for r in rgxs)))
    if not fields:
        return None, "변환 가능 필드 없음"
    lines = ['<group name="sigma_l3_validation,">',
             f'  <rule id="{L3_RULE_ID}" level="12">', '    <if_group>sysmon</if_group>']
    for wf, rg in fields:
        lines.append(f'    <field name="{wf}" type="pcre2">{rg}</field>')
    lines += [f'    <description>[L3-AI-SIGMA] {rule.get("title","")}</description>',
              '  </rule>', '</group>']
    return "\n".join(lines), None

def apply_rule(xml):
    try:
        ex = subprocess.run(["docker", "exec", WAZUH_CONTAINER, "cat", LOCAL_RULES],
                            capture_output=True, text=True).stdout
        cleaned = re.sub(r'<group name="sigma_l3_validation,">.*?</group>', "",
                         ex, flags=re.DOTALL).strip()
        new = (cleaned + "\n" + xml).strip() + "\n"
        w = subprocess.run(["docker", "exec", "-i", WAZUH_CONTAINER, "sh", "-c",
                            f"cat > {LOCAL_RULES}"], input=new, text=True, capture_output=True)
        if w.returncode != 0:
            return False, w.stderr
        subprocess.run(["docker", "exec", WAZUH_CONTAINER,
                        "/var/ossec/bin/wazuh-control", "restart"],
                       capture_output=True, text=True, timeout=120)
        return True, "적용+재시작 완료"
    except Exception as e:
        return False, str(e)

def rollback_rule():
    try:
        ex = subprocess.run(["docker", "exec", WAZUH_CONTAINER, "cat", LOCAL_RULES],
                            capture_output=True, text=True).stdout
        cleaned = re.sub(r'<group name="sigma_l3_validation,">.*?</group>', "",
                         ex, flags=re.DOTALL).strip() + "\n"
        subprocess.run(["docker", "exec", "-i", WAZUH_CONTAINER, "sh", "-c",
                        f"cat > {LOCAL_RULES}"], input=cleaned, text=True, capture_output=True)
        subprocess.run(["docker", "exec", WAZUH_CONTAINER,
                        "/var/ossec/bin/wazuh-control", "restart"],
                       capture_output=True, timeout=120)
    except Exception:
        pass


# ══ Slack 버튼 핸들러 ═════════════════════════════════
@app.action("gen_sigma")
def on_gen(ack, body, client):
    ack()
    val = json.loads(body["actions"][0]["value"])
    tech, ctx = val["tech"], val["ctx"]
    ch = body["channel"]["id"]; ts = body["message"]["ts"]
    client.chat_postMessage(channel=ch, thread_ts=ts, text=f"⚙️ L3: {tech} Sigma 생성 중...")

    sigma = ask_gemini(
        f"탐지엔지니어로서 {tech} 탐지 공백을 메울 Sigma 룰을 YAML로만 출력(설명·펜스 없이). "
        f"Windows process_creation, detection에 selection+condition, "
        f"Image/CommandLine/ParentImage 활용, 오탐 줄이게 구체적, tags에 attack.{tech.lower()}. "
        f"관찰맥락: {ctx}", 600)
    sigma = re.sub(r"^```ya?ml\s*|```$", "", sigma, flags=re.MULTILINE).strip()

    xml, err = sigma_to_xml(sigma)
    if err:
        client.chat_postMessage(channel=ch, thread_ts=ts,
                                text=f"❌ 변환 실패: {err}\n```\n{sigma}\n```")
        return
    ok, msg = apply_rule(xml)
    status = "✅ Wazuh 적용 완료 (검증은 별도 validate_sigma로 수행)" if ok else f"❌ 적용 실패: {msg}"
    _pending[ts] = {"sigma": sigma, "technique": tech, "xml": xml}
    client.chat_postMessage(channel=ch, thread_ts=ts, text="L3 Sigma 생성 결과",
        blocks=[
            {"type": "section", "text": {"type": "mrkdwn",
             "text": f"*🛠️ L3 생성 Sigma ({tech})*\n```\n{sigma[:2400]}\n```\n{status}"}},
            {"type": "actions", "elements": [
                {"type": "button", "text": {"type": "plain_text", "text": "✅ 운영 반영"},
                 "style": "primary", "action_id": "approve_sigma", "value": ts},
                {"type": "button", "text": {"type": "plain_text", "text": "❌ 거부"},
                 "style": "danger", "action_id": "reject_sigma", "value": ts}]}])

@app.action("approve_sigma")
def on_approve(ack, body, client):
    ack()
    ts = body["actions"][0]["value"]
    ch = body["channel"]["id"]; thr = body["message"]["ts"]
    user = body["user"]["username"]
    info = _pending.get(ts)
    tech = info["technique"] if info else "?"
    report = ""
    if info:
        report = ask_gemini(
            f"SOC 침해대응 리포트를 개조식으로 간결히. 사고개요/탐지내용/대응/후속조치 각 1~2줄. "
            f"기법:{tech} Sigma:{info['sigma'][:400]}", 400)
    client.chat_postMessage(channel=ch, thread_ts=thr,
        text=f"✅ *{user}* 승인 — {tech} 룰 운영 반영 완료\n\n*📋 IR 리포트:*\n{report}")

@app.action("reject_sigma")
def on_reject(ack, body, client):
    ack()
    ch = body["channel"]["id"]; thr = body["message"]["ts"]
    user = body["user"]["username"]
    rollback_rule()
    client.chat_postMessage(channel=ch, thread_ts=thr, text=f"❌ *{user}* 거부 — 룰 롤백 완료")


# ══ 백그라운드 폴링 루프 ══════════════════════════════
def polling_loop():
    # 실행 시점을 기준선으로 — 이 시각 이후 발생한 얼럿만 처리
    start_ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    print(f"[폴링] 시작 — {POLL_INTERVAL}s, level>={MIN_LEVEL}")
    print(f"[*] 기준 시각: {start_ts} (이후 발생 얼럿만 처리)")
    seen = set()   # 이번 실행 중 중복 방지용 (파일 불필요)
    while True:
        try:
            new = [a for a in poll_wazuh(after_ts=start_ts) if a["_id"] not in seen]
            for a in reversed(new):
                c = triage(a)
                tts = post_l1(c)
                if c["verdict"] in ("탐지공백", "탐지됨"):
                    post_l2(c, tts)
                seen.add(a["_id"])
                print(f"    → {c['mitre_id']} L{c['level']} [{c['verdict']}]")
                time.sleep(1)
        except Exception as e:
            print(f"[!] 폴링 오류: {e}")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    print("[SOC AI Agent] L1+L2+L3 통합 시작")
    threading.Thread(target=polling_loop, daemon=True).start()
    print("[L3] Socket Mode 버튼 대기")
    SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"]).start()
