import Foundation
import Network

final class UnixSocketProtocol: URLProtocol {
    static let socketPath = LocalAppPaths.backendSocketPath
    static let pseudoHost = "backend"

    // MARK: - Connection Pool

    private static var pooledConnection: NWConnection?
    private static var isPooledConnectionBusy = false
    private static let poolLock = NSLock()

    static func register() {
        URLProtocol.registerClass(UnixSocketProtocol.self)
    }

    // MARK: - Per-request State

    private var connection: NWConnection?
    private var ownsPooledConnection = false
    private var responseBuffer = Data()
    private var headerEnd = 0
    private var statusCode = 500
    private var responseHeaders: [String: String] = [:]
    private var timeoutWorkItem: DispatchWorkItem?
    private var requestStartTime: CFAbsoluteTime = 0
    private var requestBody: Data?

    // MARK: - URLProtocol

    override class func canInit(with request: URLRequest) -> Bool {
        request.url?.host == pseudoHost
    }

    override class func canonicalRequest(for request: URLRequest) -> URLRequest {
        request
    }

    override func startLoading() {
        let t0 = CFAbsoluteTimeGetCurrent()
        requestStartTime = t0
        guard let url = request.url else {
            client?.urlProtocol(self, didFailWithError: URLError(.badURL))
            return
        }

        // URLSession strips httpBody for custom URLProtocols and provides it via
        // httpBodyStream instead. Read the body from whichever source is available.
        if let body = request.httpBody {
            requestBody = body
        } else if let stream = request.httpBodyStream {
            stream.open()
            var data = Data()
            var buffer = [UInt8](repeating: 0, count: 4096)
            while stream.hasBytesAvailable {
                let count = stream.read(&buffer, maxLength: buffer.count)
                if count > 0 { data.append(buffer, count: count) } else { break }
            }
            stream.close()
            requestBody = data.isEmpty ? nil : data
        }

        let connectionStart = CFAbsoluteTimeGetCurrent()
        let timeout = request.timeoutInterval > 0 ? request.timeoutInterval : 30
        let workItem = DispatchWorkItem { [weak self] in
            self?.handleTimeout()
        }
        timeoutWorkItem = workItem
        DispatchQueue.global().asyncAfter(deadline: .now() + timeout, execute: workItem)

        var targetPath = url.path
        if let query = url.query, !query.isEmpty {
            targetPath += "?\(query)"
        }

        var raw = "\(request.httpMethod ?? "GET") \(targetPath) HTTP/1.1\r\n"
        raw += "Host: \(Self.pseudoHost)\r\n"

        if let headers = request.allHTTPHeaderFields {
            for (key, value) in headers {
                raw += "\(key): \(value)\r\n"
            }
        }

        if let body = requestBody {
            raw += "Content-Length: \(body.count)\r\n"
        }
        raw += "Connection: keep-alive\r\n"
        raw += "\r\n"

        // Acquire connection from pool or create new
        let conn: NWConnection
        Self.poolLock.lock()
        if !Self.isPooledConnectionBusy, let pooled = Self.pooledConnection, pooled.state == .ready {
            Self.isPooledConnectionBusy = true
            ownsPooledConnection = true
            connection = pooled
            conn = pooled
            Self.poolLock.unlock()
            let connMs = Int((CFAbsoluteTimeGetCurrent() - connectionStart) * 1000)
            if connMs > 100 {
                let line = "[UnixSocket] pool_acq=\(connMs)ms\n"
                print(line)
                if let d = line.data(using: .utf8) { try? d.write(to: LocalAppPaths.logFile("session_timing.log")) }
            }
            sendRequest(raw, on: conn)
        } else {
            Self.poolLock.unlock()
            conn = NWConnection(to: NWEndpoint.unix(path: Self.socketPath), using: .tcp)
            connection = conn
            let newConnStart = CFAbsoluteTimeGetCurrent()
            conn.stateUpdateHandler = { [weak self] state in
                switch state {
                case .ready:
                    let connMs = Int((CFAbsoluteTimeGetCurrent() - newConnStart) * 1000)
                    if connMs > 100 {
                        let line = "[UnixSocket] new_conn=\(connMs)ms\n"
                        print(line)
                        if let d = line.data(using: .utf8) { try? d.write(to: LocalAppPaths.logFile("session_timing.log")) }
                    }
                    self?.sendRequest(raw, on: conn)
                case .failed(let error):
                    self?.fail(with: error)
                case .waiting(let error):
                    // Socket not ready yet — fail fast so caller can retry
                    self?.fail(with: error)
                default:
                    break
                }
            }
            conn.start(queue: .global())
        }
    }

    override func stopLoading() {
        timeoutWorkItem?.cancel()
        timeoutWorkItem = nil

        // Discard pooled connection on cancellation — may have unread data
        if ownsPooledConnection {
            Self.poolLock.lock()
            Self.pooledConnection?.cancel()
            Self.pooledConnection = nil
            Self.isPooledConnectionBusy = false
            Self.poolLock.unlock()
        } else {
            connection?.cancel()
        }
        connection = nil
    }

    // MARK: - I/O

    private func sendRequest(_ raw: String, on conn: NWConnection) {
        var packet = raw.data(using: .utf8) ?? Data()
        if let body = requestBody {
            packet.append(body)
        }
        conn.send(content: packet, completion: .contentProcessed { [weak self] error in
            if let error {
                self?.fail(with: error)
            } else {
                self?.readResponse(conn)
            }
        })
    }

    private func readResponse(_ conn: NWConnection) {
        conn.receive(minimumIncompleteLength: 1, maximumLength: 65536) { [weak self] data, _, _, error in
            guard let self else { return }

            if let error {
                self.fail(with: error)
                return
            }

            if let data {
                self.responseBuffer.append(data)

                if self.headerEnd == 0,
                   let range = self.responseBuffer.range(of: Data("\r\n\r\n".utf8)) {
                    self.headerEnd = range.endIndex
                    self.parseHeaders(String(data: self.responseBuffer[0..<range.startIndex], encoding: .utf8) ?? "")
                }

                if self.headerEnd > 0 {
                    let body = self.responseBuffer[self.headerEnd...]
                    if let cl = self.responseHeaders["content-length"],
                       let len = Int(cl),
                       body.count >= len {
                        self.complete(with: Data(body.prefix(len)))
                        return
                    }
                }

                self.readResponse(conn)
            } else {
                // Server closed connection — deliver what we have
                let body = self.headerEnd > 0 ? Data(self.responseBuffer[self.headerEnd...]) : Data()
                self.complete(with: body)
            }
        }
    }

    private func parseHeaders(_ raw: String) {
        let lines = raw.components(separatedBy: "\r\n")
        for line in lines.dropFirst() {
            let parts = line.components(separatedBy: ": ")
            if parts.count >= 2 {
                responseHeaders[parts[0].lowercased()] = parts.dropFirst().joined(separator: ": ")
            }
        }
        if let first = lines.first {
            let parts = first.components(separatedBy: " ")
            if parts.count >= 2, let code = Int(parts[1]) {
                statusCode = code
            }
        }
    }

    // MARK: - Completion / Cleanup

    private func complete(with body: Data) {
        let elapsed = Int((CFAbsoluteTimeGetCurrent() - requestStartTime) * 1000)
        timeoutWorkItem?.cancel()
        timeoutWorkItem = nil

        if let url = request.url,
           let response = HTTPURLResponse(
            url: url,
            statusCode: statusCode,
            httpVersion: "HTTP/1.1",
            headerFields: responseHeaders
           ) {
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        }
        if !body.isEmpty {
            client?.urlProtocol(self, didLoad: body)
        }
        client?.urlProtocolDidFinishLoading(self)

        if elapsed > 500 {
            let timingLine = "[UnixSocket] \(request.httpMethod ?? "?") \(request.url?.path ?? "?") → \(statusCode) in \(elapsed)ms (pooled=\(ownsPooledConnection))\n"
            print(timingLine)
            if let data = timingLine.data(using: .utf8) {
                let url = LocalAppPaths.logFile("session_timing.log")
                if let fh = try? FileHandle(forWritingTo: url) {
                    fh.seekToEndOfFile()
                    fh.write(data)
                    fh.closeFile()
                } else {
                    try? data.write(to: url)
                }
            }
        }

        // Return connection to pool
        returnOrCleanupConnection()
        connection = nil
    }

    private func fail(with error: Error) {
        timeoutWorkItem?.cancel()
        timeoutWorkItem = nil

        client?.urlProtocol(self, didFailWithError: error)

        // Discard pooled connection on error — it may be broken
        if ownsPooledConnection {
            Self.poolLock.lock()
            Self.pooledConnection?.cancel()
            Self.pooledConnection = nil
            Self.isPooledConnectionBusy = false
            Self.poolLock.unlock()
        } else {
            connection?.cancel()
        }
        connection = nil
    }

    private func returnOrCleanupConnection() {
        if ownsPooledConnection {
            Self.poolLock.lock()
            Self.isPooledConnectionBusy = false
            Self.poolLock.unlock()
        } else if let conn = connection {
            Self.poolLock.lock()
            if Self.pooledConnection == nil {
                Self.pooledConnection = conn
                Self.isPooledConnectionBusy = false
            } else {
                conn.cancel()
            }
            Self.poolLock.unlock()
        }
    }

    private func handleTimeout() {
        guard connection != nil || ownsPooledConnection else { return }
        let error = URLError(.timedOut)
        fail(with: error)
    }
}
