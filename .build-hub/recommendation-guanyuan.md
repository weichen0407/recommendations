# Build Hub Deployment: recommendation-guanyuan

- Service: recommendation-guanyuan
- Runtime: node20
- VM: 10.150.112.18
- Backend port: 32084
- Backend command: `PORT=32084 HOST=0.0.0.0 node server.js`
- Systemd unit: `recommendation-guanyuan.service`
- Working directory: `~/apps/recommendation-guanyuan/current`
- Internal URL: `http://10.150.112.18:32084`
- Private domain: `https://recommendation-guanyuan-weibohan.build.patsnap.info`
- Access mode: private
- Homepage analytics: enabled

## Dashboard Contract

- Dashboard URL: `/`
- Dashboard metadata/data: `GET /api/dashboard`
- Update endpoint: `POST /api/update` or `GET /api/update`
- Health endpoint: `GET /api/health`
- The `dashboard.url`, `dashboard.iframe_url`, `dashboard.api_url`, and `dashboard.update_url` fields are absolute and are derived from the request host. Internal VM calls return `http://10.150.112.18:32084/...`; Build Hub gateway calls return `https://recommendation-guanyuan-weibohan.build.patsnap.info/...`.

`/api/update` returns:

```json
{
  "ok": true,
  "status": "updated",
  "source": "local-cache",
  "dashboard": {
    "id": "recommendation-guanyuan",
    "title": "推荐系统 Guanyuan 数据",
    "url": "/",
    "api_url": "/api/dashboard",
    "update_url": "/api/update"
  },
  "steps": []
}
```

`source=local-cache` means the service recalculated the visualization files from the JSON files currently deployed with the app. To plug in a real Guandata crawler, set `RECOMMENDATION_UPDATE_COMMAND` in the systemd environment and redeploy/restart.
