#!/bin/bash
# ============================================================
# NAS IPv6 防火墙规则脚本
# 目标：外网只能访问 8443（工作台），局域网不受限制
# 安全保障：SSH 走 IPv4，ip6tables 不影响 IPv4
# ============================================================

echo "[firewall] 开始配置 IPv6 防火墙规则..."

# 清除现有 INPUT 规则（不影响 FORWARD/Docker 规则）
ip6tables -F INPUT

# 1. 放行回环接口
ip6tables -A INPUT -i lo -j ACCEPT

# 2. 放行已建立连接和相关连接
ip6tables -A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT

# 3. 放行 ICMPv6（邻居发现、路由发现等必需）
ip6tables -A INPUT -p ipv6-icmp -j ACCEPT

# 4. 放行链路本地地址（路由器、局域网设备的 fe80:: 地址）
ip6tables -A INPUT -s fe80::/10 -j ACCEPT

# 5. 动态获取并放行局域网 IPv6 前缀（proto ra 的 /64 前缀）
for prefix in $(ip -6 route show | grep "proto ra" | grep "/64" | awk "{print \$1}"); do
    echo "[firewall] 放行局域网前缀: $prefix"
    ip6tables -A INPUT -s $prefix -j ACCEPT
done

# 6. 放行工作台 8443 端口（外网需要访问）
ip6tables -A INPUT -p tcp --dport 8443 -j ACCEPT

# 7. 设置默认策略为 DROP（拒绝其他所有外网入站）
ip6tables -P INPUT DROP

echo "[firewall] IPv6 防火墙规则配置完成"
echo "[firewall] 放行: lo, ESTABLISHED, ICMPv6, fe80::/10, 局域网前缀, 8443"
echo "[firewall] 拒绝: 其他所有外网 IPv6 入站"
