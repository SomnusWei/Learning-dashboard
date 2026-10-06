"""
阿里云 DNS DDNS 更新脚本
用途：检测本机 IPv6 地址，与阿里云 DNS 解析的 AAAA 记录比对，发现变化则自动更新。
依赖：仅用 Python 标准库（urllib + hmac + hashlib + base64），无需 pip 安装第三方包。

用法：
  python3 aliyun_ddns.py --rr dashboard --domain your-domain.com --ak <AKID> --as <AKSECRET>
  python3 aliyun_ddns.py --rr dashboard --domain your-domain.com --ak $AK --as $AS --once
  python3 aliyun_ddns.py --rr dashboard --domain your-domain.com --ak $AK --as $AS --loop 300

建议放到 crontab：
  */5 * * * * /usr/bin/python3 /path/to/aliyun_ddns.py --ak XXX --as YYY --rr dashboard --domain your-domain.com --once >> /var/log/aliyun_ddns.log 2>&1
"""
import argparse
import base64
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime


ALIDNS_ENDPOINT = "https://alidns.aliyuncs.com"


def percent_encode(s: str) -> str:
    """阿里云 RPC 签名要求的 URL 编码规则。"""
    return urllib.parse.quote(s, safe="~-_")


def sign(params: dict, secret: str) -> str:
    """计算阿里云 RPC v1.0 签名（HMAC-SHA1 + base64）。"""
    items = sorted(params.items())
    canonicalized = "&".join(f"{percent_encode(k)}={percent_encode(v)}" for k, v in items)
    string_to_sign = "GET&" + percent_encode("/") + "&" + percent_encode(canonicalized)
    dig = hmac.new(
        (secret + "&").encode("utf-8"),
        string_to_sign.encode("utf-8"),
        hashlib.sha1,
    ).digest()
    return base64.b64encode(dig).decode("utf-8")


def call_api(action: str, ak: str, secret: str, extra: dict) -> dict:
    """调用阿里云 DNS OpenAPI。"""
    params = {
        "Format": "JSON",
        "Version": "2015-01-09",
        "AccessKeyId": ak,
        "SignatureMethod": "HMAC-SHA1",
        "Timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "SignatureVersion": "1.0",
        "SignatureNonce": f"{int(time.time() * 1000)}{os.getpid()}",
        "Action": action,
    }
    params.update(extra)
    params["Signature"] = sign(params, secret)
    url = ALIDNS_ENDPOINT + "/?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        return {"__http_error__": e.code, "__body__": body}
    except Exception as e:
        return {"__exception__": str(e)}


def get_local_ipv6() -> str | None:
    """获取本机全局 IPv6 地址（取第一个非临时、非 link-local 的地址）。"""
    try:
        out = subprocess_run(["ip", "-6", "addr", "show", "scope", "global"])
    except Exception:
        return None
    candidates = []
    for line in out.splitlines():
        line = line.strip()
        if not line.startswith("inet6 "):
            continue
        # 形如：inet6 xxxx:xxxx:xxxx:xxxx:xxxx:xxxx:xxxx/64 scope global dynamic noprefixroute
        addr = line.split()[1].split("/")[0]
        # 跳过临时地址（temporary），优先选 stable 的
        if "temporary" in line:
            continue
        candidates.append(addr)
    if candidates:
        return candidates[0]
    # 退化：取第一个全局地址
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("inet6 "):
            return line.split()[1].split("/")[0]
    return None


def subprocess_run(cmd: list[str]) -> str:
    import subprocess
    p = subprocess.run(cmd, capture_output=True, text=True, errors="ignore", timeout=5)
    return p.stdout or ""


def describe_records(ak: str, secret: str, domain: str, rr: str) -> list[dict] | dict:
    """查询指定子域名的所有 AAAA 解析记录。返回 list 或错误 dict。"""
    res = call_api(
        "DescribeDomainRecords",
        ak,
        secret,
        {"DomainName": domain, "RRKeyWord": rr, "Type": "AAAA"},
    )
    if "__http_error__" in res or "__exception__" in res:
        return res
    records = res.get("DomainRecords", {}).get("Record", [])
    return [r for r in records if r.get("Type") == "AAAA" and r.get("RR") == rr]


def update_record(ak: str, secret: str, record_id: str, rr: str, value: str, ttl: int = 600) -> dict:
    """更新一条解析记录。"""
    return call_api(
        "UpdateDomainRecord",
        ak,
        secret,
        {
            "RecordId": record_id,
            "RR": rr,
            "Type": "AAAA",
            "Value": value,
            "TTL": str(ttl),
        },
    )


def add_record(ak: str, secret: str, domain: str, rr: str, value: str, ttl: int = 600) -> dict:
    """新增一条解析记录。"""
    return call_api(
        "AddDomainRecord",
        ak,
        secret,
        {
            "DomainName": domain,
            "RR": rr,
            "Type": "AAAA",
            "Value": value,
            "TTL": str(ttl),
        },
    )


def delete_record(ak: str, secret: str, record_id: str) -> dict:
    """删除一条解析记录。"""
    return call_api(
        "DeleteDomainRecord",
        ak,
        secret,
        {"RecordId": record_id},
    )


def update_once(ak: str, secret: str, domain: str, rr: str, ttl: int) -> bool:
    """执行一次更新检测，返回是否成功更新。
    多条 AAAA 记录时：保留与本地 IP 一致的，删除其余，若无一致则更新第一条并删多余。
    """
    local_ip = get_local_ipv6()
    if not local_ip:
        print(f"[{datetime.now().isoformat()}] 未获取到本机全局 IPv6 地址，跳过")
        return False

    records = describe_records(ak, secret, domain, rr)
    if isinstance(records, dict) and ("__http_error__" in records or "__exception__" in records):
        print(f"[{datetime.now().isoformat()}] 查询阿里云 DNS 失败: {records}")
        return False

    if not records:
        # 不存在，新增
        res = add_record(ak, secret, domain, rr, local_ip, ttl)
        if "__http_error__" in res or "__exception__" in res:
            print(f"[{datetime.now().isoformat()}] 新增 AAAA 记录失败: {res}")
            return False
        print(f"[{datetime.now().isoformat()}] 新增 AAAA 记录成功: {rr}.{domain} -> {local_ip}")
        return True

    # 已有记录
    matching = [r for r in records if r.get("Value") == local_ip]
    others = [r for r in records if r.get("Value") != local_ip]

    if matching and not others:
        # 唯一一条且正确，无需操作
        print(f"[{datetime.now().isoformat()}] AAAA 已是最新 ({local_ip})，无需更新")
        return False

    updated = False
    # 删除所有非本地 IP 的记录
    for r in others:
        res = delete_record(ak, secret, r["RecordId"])
        if "__http_error__" in res or "__exception__" in res:
            print(f"[{datetime.now().isoformat()}] 删除旧 AAAA 失败: {res} (旧: {r.get('Value')})")
        else:
            print(f"[{datetime.now().isoformat()}] 删除旧 AAAA: {r.get('Value')}")
            updated = True

    if not matching:
        # 没有匹配的，新增一条
        res = add_record(ak, secret, domain, rr, local_ip, ttl)
        if "__http_error__" in res or "__exception__" in res:
            print(f"[{datetime.now().isoformat()}] 新增 AAAA 失败: {res}")
            return False
        print(f"[{datetime.now().isoformat()}] 新增 AAAA 成功: {rr}.{domain} -> {local_ip}")
        updated = True
    else:
        # 已存在匹配记录，保留即可
        print(f"[{datetime.now().isoformat()}] 保留匹配 AAAA: {local_ip}")
        updated = updated or False

    return updated


def main():
    ap = argparse.ArgumentParser(description="阿里云 DNS IPv6 DDNS")
    ap.add_argument("--ak", required=True, help="AccessKey ID")
    ap.add_argument("--as", dest="as_secret", required=True, help="AccessKey Secret")
    ap.add_argument("--domain", required=True, help="主域名，如 your-domain.com")
    ap.add_argument("--rr", required=True, help="主机记录，如 dashboard")
    ap.add_argument("--ttl", type=int, default=600, help="TTL 秒，默认 600")
    ap.add_argument("--once", action="store_true", help="仅执行一次后退出")
    ap.add_argument("--loop", type=int, default=0, help="循环间隔秒数，>0 时启用循环")
    args = ap.parse_args()

    if args.once or args.loop <= 0:
        update_once(args.ak, args.as_secret, args.domain, args.rr, args.ttl)
        return

    print(f"[{datetime.now().isoformat()}] 启动循环模式，间隔 {args.loop} 秒")
    while True:
        try:
            update_once(args.ak, args.as_secret, args.domain, args.rr, args.ttl)
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] 异常: {e}")
        time.sleep(args.loop)


if __name__ == "__main__":
    main()
