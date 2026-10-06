#!/bin/bash
# acme.sh 续期后重载 nginx 容器
cd /vol1/1000/learning-dashboard && docker compose restart nginx
