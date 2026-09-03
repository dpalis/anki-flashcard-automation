import Foundation
import ImageIO
import Vision

func fail(_ message: String) -> Never {
    FileHandle.standardError.write(Data((message + "\n").utf8))
    exit(1)
}

guard CommandLine.arguments.count == 2 else {
    fail("Uso: detect_visible_text.swift <imagem>")
}

let imageURL = URL(fileURLWithPath: CommandLine.arguments[1])
guard
    let source = CGImageSourceCreateWithURL(imageURL as CFURL, nil),
    let image = CGImageSourceCreateImageAtIndex(source, 0, nil)
else {
    fail("Não foi possível abrir a imagem")
}

let request = VNRecognizeTextRequest()
request.recognitionLevel = .accurate
request.usesLanguageCorrection = false
request.minimumTextHeight = 0.01

do {
    try VNImageRequestHandler(cgImage: image, options: [:]).perform([request])
} catch {
    fail("Vision não conseguiu analisar a imagem: \(error.localizedDescription)")
}

let alphanumerics = CharacterSet.alphanumerics
for observation in request.results ?? [] {
    guard let candidate = observation.topCandidates(1).first, candidate.confidence >= 0.70 else {
        continue
    }
    let value = candidate.string.trimmingCharacters(in: .whitespacesAndNewlines)
    if value.unicodeScalars.contains(where: alphanumerics.contains) {
        print(value)
    }
}
