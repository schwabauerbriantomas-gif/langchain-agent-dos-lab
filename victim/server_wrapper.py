"""Wrapper del server víctima: aplica RLIMIT_AS 2.5GB (mismo envelope que el
heap de n8n en el lab original) y arranca la app en 8123."""
import os
import resource

LIMIT = int(2.5 * 1024 * 1024 * 1024)  # 2.5 GB, igual que el heap de n8n en el lab
resource.setrlimit(resource.RLIMIT_AS, (LIMIT, LIMIT))

import uvicorn  # noqa: E402

from victim_app import app  # noqa: E402

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8124, log_level="warning")
