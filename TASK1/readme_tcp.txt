============================================================
  TCP 反转文本传输 — 课程设计项目说明文档
============================================================

一、项目概述
-----------
本项目实现了一个基于 TCP 协议的客户端-服务器应用，客户端将 ASCII 文本文件
分块发送给服务器，服务器将每个数据块反转（字节序颠倒）后返回，客户端将反
转后的数据块拼接输出。

二、文件说明
-----------
reversetcpserver.py  — TCP 服务器程序
reversetcpclient.py  — TCP 客户端程序
sample_ascii.txt     — 测试用的 ASCII 文本输入文件

三、协议设计
-----------
采用自定义应用层协议，数据包格式如下：

  ┌──────────┬──────────┬──────────────┐
  │  Type    │  Length  │     Data     │
  │ (2 bytes)│ (4 bytes)│ (Length bytes)
  └──────────┴──────────┴──────────────┘

消息类型 (Type)：
  1 — Initialization (初始化，客户端→服务器，携带总块数 N)
  2 — Agree         (确认，服务器→客户端，同意开始传输)
  3 — ReverseRequest(反转请求，客户端→服务器，携带一个数据块)
  4 — ReverseAnswer (反转应答，服务器→客户端，携带反转后的数据块)

所有多字节整数使用网络字节序（Big-Endian）。

协议流程：
  1. 客户端读取文件，按种子随机生成可变长度的块大小序列
  2. 客户端 → 服务器：Initialization (Type=1, N=总块数)
  3. 服务器 → 客户端：Agree (Type=2)
  4. 循环 N 次：
     客户端 → 服务器：ReverseRequest (Type=3, 数据块)
     服务器 → 客户端：ReverseAnswer (Type=4, 反转后的数据块)
  5. 客户端将反转块拼接，写入输出文件

四、使用方法
-----------
1. 启动服务器（先运行）：
   python reversetcpserver.py [端口号]
   默认端口：12345
   示例：python reversetcpserver.py 12345

2. 启动客户端：
   python reversetcpclient.py <服务器IP> <端口> <Lmin> <Lmax> <输入文件> [种子]
   示例：python reversetcpclient.py 127.0.0.1 12345 50 100 sample_ascii.txt 42

   参数说明：
   - Lmin：最小块大小（字节）
   - Lmax：最大块大小（字节）
   - 种子：随机数种子，用于确定性生成块大小序列（默认 42）

3. 输出：
   反转后的文本保存在 <输入文件名>_reversed.txt 中
   运行日志会记录在 client_log.txt 和 server_log.txt 中

五、功能特点
-----------
- TCP 可靠连接，确保数据不丢失
- 可变长度数据块（Lmin ~ Lmax 之间随机）
- 确定性的块大小序列（使用随机种子）
- 支持多客户端并发（服务器多线程）
- 详细的时间戳日志记录
- 逐块打印反转结果到终端

六、日志文件
-----------
client_log.txt — 客户端运行日志
server_log.txt — 服务器运行日志
每次运行会覆盖之前的日志。

七、测试示例
-----------
输入文本 sample_ascii.txt (742 字节)：

  "The quick brown fox jumps over the lazy dog near the riverbank.
   A gentle breeze blew through the open window, carrying the scent
   of spring flowers into the quiet room. Computer networks connect
   devices..."

使用参数 Lmin=50, Lmax=100, seed=42：
生成 10 个数据块：[90, 57, 51, 97, 67, 65, 64, 58, 97, 96]

每个数据块被服务器反转后返回，客户端拼接写入
sample_ascii_reversed.txt。
