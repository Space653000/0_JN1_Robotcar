import os, time
from fastapi import FastAPI
from pydantic import BaseModel
import requests
app = FastAPI()
KEY = os.environ.get("GEMINI_API_KEY","")
MODEL = os.environ.get("GEMINI_MODEL","gemini-2.0-flash")
DAILY = int(os.environ.get("CLOUD_DAILY_LIMIT","200"))
S = {"day":"","count":0,"breaker":0}
class Ask(BaseModel):
    text: str
@app.get("/health")
def health():
    return {"ok":True,"provider":"gemini","has_key":bool(KEY),"model":MODEL,"used_today":S["count"]}
@app.post("/ask")
def ask(req: Ask):
    today=time.strftime("%Y-%m-%d")
    if S["day"]!=today: S["day"]=today; S["count"]=0
    if not KEY: return {"ok":False,"source":"cloud-unavailable","reason":"no_key","reply":None}
    if time.time()<S["breaker"]: return {"ok":False,"source":"cloud-unavailable","reason":"circuit_open","reply":None}
    if S["count"]>=DAILY: return {"ok":False,"source":"cloud-quota","reason":"daily_limit","reply":None}
    try:
        url="https://generativelanguage.googleapis.com/v1beta/models/"+MODEL+":generateContent?key="+KEY
        r=requests.post(url, json={"contents":[{"parts":[{"text":req.text}]}]}, timeout=25)
        S["count"]+=1
        if r.status_code!=200:
            S["breaker"]=time.time()+30
            return {"ok":False,"source":"cloud-error","status":r.status_code,"detail":r.text[:200],"reply":None}
        d=r.json()
        reply=d["candidates"][0]["content"]["parts"][0]["text"]
        return {"ok":True,"source":"gemini","model":MODEL,"reply":reply}
    except Exception as e:
        S["breaker"]=time.time()+30
        return {"ok":False,"source":"cloud-unavailable","reason":str(e)[:120],"reply":None}
