============================================================
  UDP 可靠数据传输 — 课程设计项目说明文档
============================================================

一、项目概述
-----------
本项目实现了基于 UDP 协议模拟 TCP 可靠数据传输的客户端-服务器应用。
通过在应用层实现三次握手、GBN 滑动窗口协议、超时重传、累积确认等机制，
在不可靠的 UDP 之上构建可靠的数据传输服务。

二、文件说明
-----------
udpserver.py           — UDP 服务器程序
udpclient.py           — UDP 客户端程序
run_log.txt            — 运行日志文件（服务器和客户端共享）
readme.txt             — 本说明文档
udp_packet_capture.docx — Wireshark 抓包分析文档

三、协议设计
-----------

3.1 自定义报文头部格式（18 字节，网络字节序）

  ┌────────────┬──────────┬──────────────────────────────┐
  │  字段名    │  字节数  │  说明                        │
  ├────────────┼──────────┼──────────────────────────────┤
  │ src_port   │  2       │  源端口号                    │
  │ dst_port   │  2       │  目的端口号                  │
  │ seq        │  4       │  序列号                      │
  │ ack        │  4       │  确认号（累积确认）           │
  │ flags      │  2       │  标志位：SYN/ACK/FIN/DATA     │
  │ student_id │  2       │  学号字段（XOR 0x5A3C）       │
  │ data_len   │  2       │  数据长度（字节）             │
  │ data       │  变长    │  数据载荷                     │
  └────────────┴──────────┴──────────────────────────────┘

3.2 标志位定义
  FLAG_SYN  = 0x0001  连接建立请求
  FLAG_ACK  = 0x0002  确认
  FLAG_FIN  = 0x0004  连接终止
  FLAG_DATA = 0x0008  数据包

3.3 协议流程

阶段一：三次握手连接建立
  1. Client → Server: SYN (flags=SYN, seq=client_seq, student_id=XOR后学号)
  2. Server 验证 StudentID 字段（再次 XOR 0x5A3C，检查结果 ∈ [0,9999]）
     若非法 → 拒绝连接
     若合法 → Server → Client: SYN+ACK (flags=SYN|ACK, seq=server_seq, ack=client_seq+1)
  3. Client → Server: ACK (flags=ACK, seq=client_seq+1, ack=server_seq+1)
     连接建立完成

阶段二：GBN 可靠数据传输
  - 客户端使用固定发送窗口（400 字节）
  - 每个数据包大小在 40~80 字节之间随机
  - 总共发送 30 个数据包
  - 服务器随机丢弃数据包（模拟丢包，默认 20% 概率）
  - 服务器使用累积确认（GBN 接收端）
  - 客户端超时重传未确认的包
  - 自适应超时时间（基于 RTT 均值 + 4×标准差）

阶段三：连接终止
  1. Client → Server: FIN
  2. Server → Client: FIN+ACK

四、使用方法
-----------
环境要求：
  - Python 3.6+
  - pandas 库（pip install pandas）
  - 服务器和客户端可在同一台机器上运行（使用 127.0.0.1）

启动服务器：
  python udpserver.py [端口号] [丢包率]
  默认端口：12346
  默认丢包率：0.2（20%）
  示例：python udpserver.py 12346 0.2

启动客户端：
  python udpclient.py <服务器IP> <端口> [学号后4位] [初始超时ms]
  示例：python udpclient.py 127.0.0.1 12346 2412 300

  参数说明：
  - 学号后4位：用于 StudentID 验证（与 0x5A3C XOR）
  - 初始超时：初始超时时间（毫秒），之后根据 RTT 自适应调整

五、输出说明
-----------
客户端每发送和确认一个数据包都会打印：
  发送："第n个（第x~y字节）client端已经发送"
  确认："第n个（第x~y字节）server端已经收到，RTT是xxxms，server系统时间=HH:MM:SS"
  重传："重传第n个（第x~y字节）数据包"

传输完成后打印汇总统计：
  丢包率：xx%（按 30 / 实际发送总数 计算）
  最大RTT、最小RTT、平均RTT、RTT标准差

六、功能特点
-----------
- 三次握手连接建立（模拟 TCP）
- StudentID 字段验证（XOR 运算）
- 模拟丢包（服务器随机丢弃）
- GBN 滑动窗口协议（固定 400 字节窗口）
- 累积确认机制
- 超时重传（自适应超时计算）
- RTT 统计（使用 pandas）
- 详细的运行日志（run_log.txt）
- 发送窗口流量控制

七、关键实现说明
--------------
1. GBN 协议核心：client 维护 base（最早未确认包）和 next_seq（下一个待发包）
   - 窗口内可发送多包（按字节数 400 限制）
   - 收到累积 ACK 时滑动窗口
   - 超时时重传 base 到 next_seq-1 的所有包

2. 自适应超时：
   - 初始值：命令行指定的初始超时（默认 300ms）
   - 收集 ≥3 个 RTT 样本后开始计算
   - 公式：avg_RTT + 4 × std_RTT
   - 限制范围：[初始超时, 5000ms]

3. 丢包模拟：
   - 服务器收到 DATA 包时，以 drop_rate 概率不发送 ACK
   - 不影响客户端→服务器的数据包（仅模拟 ACK 丢失）
   - 丢包率可在命令行指定

八、Wireshark 抓包
-----------------
使用 Wireshark 抓取 loopback 接口的 UDP 流量：
  过滤器：udp.port == 12346
  可观察：SYN、SYN+ACK、ACK、DATA、FIN 等自定义报文
