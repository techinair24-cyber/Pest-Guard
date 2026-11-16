import json
import os
import re
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

api_key = os.getenv("FAST2SMS_API_KEY")
number = os.getenv("FAST2SMS_TEST_NUMBER")

if not api_key or not number:
    raise SystemExit("Missing API key or test number in .env")

if not re.fullmatch(r"[6-9]\d{9}", number):
    raise SystemExit("Enter a valid 10-digit Indian mobile number.")

payload = {
    "route": "q",
    "message": "Pest Guard test alert. Fast2SMS API connection test.",
    "numbers": number,
    "sms_details": "1",
}

request = Request(
    "https://www.fast2sms.com/dev/bulkV2",
    data=json.dumps(payload).encode("utf-8"),
    headers={
        "Authorization": api_key,
        "Content-Type": "application/json",
        "Accept": "application/json",
    },
    method="POST",
)

try:
    with urlopen(request, timeout=30) as response:
        result = response.read().decode("utf-8")
        print("HTTP Status:", response.status)
        print("Fast2SMS Response:", result)

except HTTPError as error:
    print("HTTP Error:", error.code)
    print(error.read().decode("utf-8"))

except URLError as error:
    print("Connection Error:", error.reason)
