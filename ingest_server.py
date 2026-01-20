from fastapi import FastAPI
import subprocess
import os

app = FastAPI(title="RUSH X Ingest Trigger")

@app.get("/run-ingest")
def run_ingest():
    try:
        # Run the X ingestion script
        result = subprocess.run(
            ["python", "ingest_x_only.py"],
            capture_output=True,
            text=True,
            timeout=600  # 10 min max runtime to prevent hangs
        )
        return {
            "status": "success",
            "stdout": result.stdout,
            "stderr": result.stderr,
            "return_code": result.returncode
        }
    except subprocess.TimeoutExpired:
        return {"status": "error", "message": "Ingestion timed out after 10 minutes"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
