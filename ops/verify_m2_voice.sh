#!/usr/bin/env bash
# M2 voice/vision verification gates. Prints PASS/FAIL per gate; exit 1 if any fail.
set -uo pipefail
B="http://127.0.0.1:${BRAIN_PORT:-21500}"
pass=0; fail=0
chk(){ if [ "$1" = "1" ]; then echo "PASS  $2"; pass=$((pass+1)); else echo "FAIL  $2  -> $3"; fail=$((fail+1)); fi; }

# G1 brain+core health
H=$(curl -s "$B/health"); echo "$H" | grep -q '"ok": *true' && g=1 || g=0
chk "$g" "G1 brain+asr+tts+ollama health" "$H"

# G2 engines actually loaded (asr sensevoice/whisper, tts kokoro/piper)
AE=$(curl -s "http://127.0.0.1:21501/health" 2>/dev/null || echo "{}")   # needs debug ports
TE=$(curl -s "http://127.0.0.1:21502/health" 2>/dev/null || echo "{}")
echo "  asr:$AE  tts:$TE  (empty = debug ports off; optional)"

# G3 LLM chat path (text in -> reply out, no mic)
R=$(curl -s -X POST "$B/ask" -H 'content-type: application/json' -d '{"text":"用一句話說你好","speak":false}')
echo "$R" | grep -q '"reply"' && [ "$(echo "$R" | python3 -c 'import sys,json;print(len(json.load(sys.stdin).get("reply","")))')" -gt 0 ] && g=1 || g=0
chk "$g" "G3 LLM chat reply" "$R"

# G4 intent routing (chat vs vision)
R=$(curl -s -X POST "$B/ask" -H 'content-type: application/json' -d '{"text":"前面有什麼","speak":false}')
echo "$R" | grep -q '"intent": *"state"' && g=1 || g=0
chk "$g" "G4 intent router -> state" "$R"

# G5 TTS synth+play (speak=true) — listen for audio on the earphone
R=$(curl -s -X POST "$B/ask" -H 'content-type: application/json' -d '{"text":"測試語音輸出","speak":true}')
echo "$R" | grep -q '"played": *true' && g=1 || g=0
chk "$g" "G5 TTS played on device" "$R"

echo "-----"; echo "PASS=$pass FAIL=$fail"
[ "$fail" = "0" ]
