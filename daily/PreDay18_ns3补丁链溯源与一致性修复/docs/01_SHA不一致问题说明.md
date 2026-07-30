# SHA 不一致问题说明

Git blob 的权威 SHA-256 是以对象原始字节计算。Windows checkout 因全局 `core.autocrlf=true` 变为 CRLF；三份文件的 checkout SHA 因此不同，但 LF 归一化后均与 Git blob 相同。P2、P3 的旧 manifest SHA 仍不等于对应 Git blob 原始字节或任一换行归一化形式。
