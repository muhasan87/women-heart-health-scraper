import requests

url = "https://www.abc.net.au/news/health"
response = requests.get(url, timeout=15)

print("Status code:", response.status_code)
print(response.text[:500])
