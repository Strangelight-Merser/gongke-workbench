// 读取最终 MP4 抽帧，辅助查找不应出镜的路径和调试字段；不控制屏幕。
import Foundation
import Vision
import ImageIO
let folder=URL(fileURLWithPath:CommandLine.arguments[1])
let files=try FileManager.default.contentsOfDirectory(at:folder,includingPropertiesForKeys:nil).filter{$0.pathExtension=="jpg" || $0.pathExtension=="png"}.sorted{$0.path<$1.path}
for file in files {
 let request=VNRecognizeTextRequest();request.recognitionLevel = .accurate;request.recognitionLanguages=["zh-Hans","en-US"]
 try VNImageRequestHandler(url:file).perform([request])
 let text=(request.results ?? []).compactMap{$0.topCandidates(1).first?.string}.joined(separator:"\n")
 let data=try JSONSerialization.data(withJSONObject:["file":file.lastPathComponent,"text":text],options:[.sortedKeys])
 print(String(data:data,encoding:.utf8)!)
}
