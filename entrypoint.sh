#!/bin/sh
[ -f /app/config.json ] || echo '{}' > /app/config.json
exec streamlit run app.py --server.port=8501 --server.address=0.0.0.0
