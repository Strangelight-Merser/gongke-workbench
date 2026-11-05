// 只采集明确传入的自有进程窗口，不录制桌面或其他应用。
import AppKit
import ScreenCaptureKit
import AVFoundation

final class Capture: NSObject, SCStreamOutput {
    let out: URL
    var frames: [[String:Any]] = []
    let queue = DispatchQueue(label: "gongke.window.frames")
    init(_ out: URL) { self.out = out }
    func stream(_ stream: SCStream, didOutputSampleBuffer sample: CMSampleBuffer, of type: SCStreamOutputType) {
        guard type == .screen, sample.isValid, let buffer = sample.imageBuffer else { return }
        let bitmap = NSBitmapImageRep(ciImage: CIImage(cvPixelBuffer: buffer))
        guard let jpeg = bitmap.representation(using: .jpeg, properties: [.compressionFactor: 0.93]) else { return }
        let file = String(format: "%06d.jpg", frames.count)
        try! jpeg.write(to: out.appendingPathComponent("frames/" + file))
        frames.append(["file":file, "timestamp":Date().timeIntervalSince1970])
    }
}
@main struct Main {
    static func main() async {
        do { try await record() }
        catch { fputs("窗口录制失败：\(error)\n", stderr); exit(1) }
    }
    static func record() async throws {
        let pid = Int32(CommandLine.arguments[1])!, out = URL(fileURLWithPath: CommandLine.arguments[2])
        let duration = Double(CommandLine.arguments[3])!
        try FileManager.default.createDirectory(at: out.appendingPathComponent("frames"), withIntermediateDirectories:true)
        let content = try await SCShareableContent.excludingDesktopWindows(true, onScreenWindowsOnly:false)
        guard let window = content.windows.filter({$0.owningApplication?.processID == pid && $0.frame.width > 500 && $0.frame.height > 300}).max(by: {$0.frame.width*$0.frame.height < $1.frame.width*$1.frame.height}) else { fatalError("自有 PID 无可录制窗口") }
        let config = SCStreamConfiguration()
        config.width = 1920; config.height = Int(1920 * window.frame.height / window.frame.width) / 2 * 2
        config.minimumFrameInterval = CMTime(value:1,timescale:30)
        config.showsCursor = true; config.queueDepth = 5
        let capture = Capture(out), stream = SCStream(filter:SCContentFilter(desktopIndependentWindow:window), configuration:config, delegate:nil)
        try stream.addStreamOutput(capture,type:.screen,sampleHandlerQueue:capture.queue)
        let started = Date().timeIntervalSince1970 * 1000
        try await stream.startCapture()
        print("RECORDING PID \(pid) window \(window.windowID)")
        try await Task.sleep(for:.seconds(duration))
        try await stream.stopCapture()
        capture.queue.sync {}
        let data: [String:Any] = ["started":started,"ended":Date().timeIntervalSince1970*1000,"frames":capture.frames,"pid":pid,"window":window.windowID,"source":"ScreenCaptureKit 原生应用窗口连续录屏"]
        try JSONSerialization.data(withJSONObject:data,options:.prettyPrinted).write(to:out.appendingPathComponent("recording.json"))
        guard !capture.frames.isEmpty else { fatalError("录屏为空") }
    }
}
