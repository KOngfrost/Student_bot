#!/bin/sh
# Временный e2e-тест страниц панели внутри контейнера (удалить после аудита).
set -u
BASE=http://localhost:8000
CJ=/tmp/cj_$$.txt
rm -f "$CJ"
curl -s -c "$CJ" "$BASE/auth/login" -o /tmp/login.html || { echo "login page fetch failed"; exit 1; }
TOKEN=$(sed -n 's/.*name="csrf_token" value="\([^"]*\)".*/\1/p' /tmp/login.html | head -1)
echo "csrf_token ok"
curl -s -b "$CJ" -c "$CJ" -o /tmp/login_result.html -w 'LOGIN: %{http_code}\n' \
  -X POST \
  --data-urlencode "username=$WEB_ADMIN_USERNAME" \
  --data-urlencode "password=$WEB_ADMIN_PASSWORD" \
  --data-urlencode "csrf_token=$TOKEN" \
  "$BASE/auth/login"
for p in / /knowledge/ /faq/ /events/ /admin/admins/ /logs/ /tickets/ /dept/1/; do
  code=$(curl -s -b "$CJ" -o /tmp/page.html -w '%{http_code}' "$BASE$p")
  echo "$p -> $code"
  if [ "$code" != "200" ]; then
    echo "---- body head ----"
    head -c 300 /tmp/page.html
    echo ""
  fi
done
rm -f "$CJ"
