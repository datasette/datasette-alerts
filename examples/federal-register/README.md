

```
curl -G "https://www.federalregister.gov/api/v1/documents.json" \
  --data-urlencode "per_page=20" \
  --data-urlencode "conditions[publication_date][lte]=2025-01-31" \
  -H "accept: */*"

```