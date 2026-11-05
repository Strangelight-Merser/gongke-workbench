// macOS 15+ 原始窗口采集：只允许启动者明确传入的自有 PID；保留系统光标，不画叠层。
import AppKit
import ScreenCaptureKit
import AVFoundation

final class RecordingState: NSObject, SCRecordingOutputDelegate {
    var started = false
    var finished = false
    var failure: Error?
    func recordingOutputDidStartRecording(_ recordingOutput: SCRecordingOutput) { started = true }
    func recordingOutputDidFinishRecording(_ recordingOutput: SCRecordingOutput) { finished = true }
    func recordingOutput(_ recordingOutput: SCRecordingOutput, didFailWithError error: Error) { failure = error }
}
@main struct Capture {
    static func main() async {
        do { try await run() } catch { fputs("原始录屏未完成：\(error)\n", stderr); exit(1) }
    }
    static func run() async throws {
        guard CommandLine.arguments.count == 3, !CommandLine.arguments[1].isEmpty else {
            throw NSError(domain:"Arguments",code:1,userInfo:[NSLocalizedDescriptionKey:"用法：window-capture 自有PID列表 输出目录"])
        }
        guard CGPreflightScreenCaptureAccess() else {
            throw NSError(domain:"ScreenRecordingPermission",code:1,userInfo:[NSLocalizedDescriptionKey:"系统未授权屏幕录制；未生成替代录屏。请为启动本进程的 Claude 应用开启权限。"])
        }
        let allowed = Set(CommandLine.arguments[1].split(separator:",").compactMap{Int32($0)})
        let output = URL(fileURLWithPath:CommandLine.arguments[2])
        guard let initial = Int32(CommandLine.arguments[1].split(separator:",")[0]) else { throw NSError(domain:"PID",code:1) }
        try FileManager.default.createDirectory(at:output,withIntermediateDirectories:true)
        let movie = output.appendingPathComponent("capture.mp4")
        guard !FileManager.default.fileExists(atPath:movie.path) else { throw NSError(domain:"OutputExists",code:1) }
        func filter(_ pid:Int32) async throws -> SCContentFilter {
            guard allowed.contains(pid) else { throw NSError(domain:"ForeignPID",code:1) }
            let content = try await SCShareableContent.excludingDesktopWindows(true,onScreenWindowsOnly:false)
            guard let window = content.windows.filter({$0.owningApplication?.processID == pid && $0.frame.width>500 && $0.frame.height>300}).max(by:{$0.frame.width*$0.frame.height < $1.frame.width*$1.frame.height}) else { throw NSError(domain:"OwnedWindowMissing",code:Int(pid)) }
            return SCContentFilter(desktopIndependentWindow:window)
        }
        let config = SCStreamConfiguration()
        config.width=2560;config.height=1440
        config.minimumFrameInterval=CMTime(value:1,timescale:60)
        config.showsCursor=true;config.queueDepth=8;config.ignoreShadowsSingleWindow=true
        config.capturesAudio=false;config.captureMicrophone=false
        let recordingConfig=SCRecordingOutputConfiguration()
        recordingConfig.outputURL=movie;recordingConfig.videoCodecType = .h264;recordingConfig.outputFileType = .mp4
        let state=RecordingState(),recording=SCRecordingOutput(configuration:recordingConfig,delegate:state)
        let stream=SCStream(filter:try await filter(initial),configuration:config,delegate:nil)
        try stream.addRecordingOutput(recording)
        try await stream.startCapture()
        while !state.started { if let error=state.failure {throw error};try await Task.sleep(for:.milliseconds(20)) }
        try Data("ready".utf8).write(to:output.appendingPathComponent("ready"))
        var consumed=0,events:[[String:Any]]=[],stop=false
        let commandFile=output.appendingPathComponent("commands.jsonl")
        while !stop {
            if let error=state.failure {throw error}
            let lines=(try? String(contentsOf:commandFile,encoding:.utf8).split(separator:"\n")) ?? []
            for line in lines.dropFirst(consumed) {
                let command=try JSONSerialization.jsonObject(with:Data(line.utf8)) as! [String:Any]
                if let pid=command["pid"] as? Int32 {try await stream.updateContentFilter(filter(pid));events.append(["seconds":recording.recordedDuration.seconds,"description":"切换到自有窗口","pid":pid])}
                if let label=command["event"] as? String {events.append(["seconds":recording.recordedDuration.seconds,"description":label])}
                if command["stop"] as? Bool == true {stop=true}
            }
            consumed=lines.count
            try await Task.sleep(for:.milliseconds(20))
        }
        try await stream.stopCapture()
        while !state.finished {if let error=state.failure {throw error};try await Task.sleep(for:.milliseconds(20))}
        let report:[String:Any]=["source":"ScreenCaptureKit 自有窗口原始采集","allowed_pids":Array(allowed),"system_cursor":true,"overlays":false,"width":2560,"height":1440,"requested_fps":60,"duration":recording.recordedDuration.seconds,"events":events]
        try JSONSerialization.data(withJSONObject:report,options:[.prettyPrinted,.sortedKeys]).write(to:output.appendingPathComponent("events.json"))
    }
}
