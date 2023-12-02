#web: gunicorn -w 1 -k uvicorn.workers.UvicornWorker --log-level debug main:app
web: uvicorn main:app --workers 4 #--host=0.0.0.0 --port=${PORT:-5000}
