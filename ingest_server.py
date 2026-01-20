from fastapi import FastAPI
import subprocess
import os

app = FastAPI()

@app.get("/run-ingest")
def run_ingest():
    try:
        # Run the X ingestion script
        result = subprocess.run(["python", "ingest_x_only.py"], capture_output=True, text=True)
        return {
            "status": "success",
            "output": result.stdout,
            "error": result.stderr
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}
