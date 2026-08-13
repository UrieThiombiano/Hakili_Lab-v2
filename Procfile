release: python manage.py collectstatic --noinput && python manage.py migrate --noinput
web: gunicorn hakili.wsgi:application --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 180 --access-logfile - --error-logfile -
