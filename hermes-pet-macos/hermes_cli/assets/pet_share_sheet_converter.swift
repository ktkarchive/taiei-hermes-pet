import AppKit
import CoreGraphics
import Foundation

struct FrameSpec {
    let key: String
    let row: Int
    let column: Int
    let file: String
}

struct AnimationSpec {
    let key: String
    let row: Int
    let frames: Int
}

let cellWidth = 192
let cellHeight = 208
let fullSize = 512
let frames = [
    FrameSpec(key: "idle", row: 0, column: 0, file: "hermes_pet_idle"),
    FrameSpec(key: "blink", row: 0, column: 1, file: "hermes_pet_blink"),
    FrameSpec(key: "working", row: 7, column: 0, file: "hermes_pet_working"),
    FrameSpec(key: "review", row: 8, column: 0, file: "hermes_pet_review"),
]
let animations = [
    AnimationSpec(key: "idle", row: 0, frames: 6),
    AnimationSpec(key: "running-right", row: 1, frames: 8),
    AnimationSpec(key: "running-left", row: 2, frames: 8),
    AnimationSpec(key: "waving", row: 3, frames: 4),
    AnimationSpec(key: "jumping", row: 4, frames: 5),
    AnimationSpec(key: "failed", row: 5, frames: 8),
    AnimationSpec(key: "waiting", row: 6, frames: 6),
    AnimationSpec(key: "running", row: 7, frames: 6),
    AnimationSpec(key: "review", row: 8, frames: 6),
]

func fail(_ message: String) -> Never {
    FileHandle.standardError.write((message + "\n").data(using: .utf8)!)
    exit(1)
}

func parseArguments() -> (URL, URL, Int) {
    let args = CommandLine.arguments
    if args.count != 4 {
        fail("usage: pet_share_sheet_converter <spritesheet.webp> <output-dir> <size>")
    }
    let size = max(56, min(Int(args[3]) ?? 84, 160))
    return (
        URL(fileURLWithPath: args[1]),
        URL(fileURLWithPath: args[2], isDirectory: true),
        size
    )
}

func loadSpritesheet(_ url: URL) -> CGImage {
    guard let image = NSImage(contentsOf: url) else {
        fail("could not load spritesheet: \(url.path)")
    }
    var rect = CGRect(origin: .zero, size: image.size)
    guard let cgImage = image.cgImage(forProposedRect: &rect, context: nil, hints: nil) else {
        fail("could not decode spritesheet: \(url.path)")
    }
    if cgImage.width < cellWidth * 8 || cgImage.height < cellHeight * 9 {
        fail("spritesheet is too small: \(cgImage.width)x\(cgImage.height)")
    }
    return cgImage
}

func renderSquare(_ crop: CGImage, size: Int) -> CGImage {
    let colorSpace = CGColorSpaceCreateDeviceRGB()
    let bitmapInfo = CGImageAlphaInfo.premultipliedLast.rawValue
    guard let context = CGContext(
        data: nil,
        width: size,
        height: size,
        bitsPerComponent: 8,
        bytesPerRow: 0,
        space: colorSpace,
        bitmapInfo: bitmapInfo
    ) else {
        fail("could not create render context")
    }

    context.clear(CGRect(x: 0, y: 0, width: size, height: size))
    context.interpolationQuality = .none
    let scale = min(CGFloat(size) / CGFloat(crop.width), CGFloat(size) / CGFloat(crop.height))
    let drawWidth = CGFloat(crop.width) * scale
    let drawHeight = CGFloat(crop.height) * scale
    let drawRect = CGRect(
        x: (CGFloat(size) - drawWidth) / 2,
        y: (CGFloat(size) - drawHeight) / 2,
        width: drawWidth,
        height: drawHeight
    )
    context.draw(crop, in: drawRect)
    guard let image = context.makeImage() else {
        fail("could not render output image")
    }
    return image
}

func writePNG(_ image: CGImage, to url: URL) {
    let rep = NSBitmapImageRep(cgImage: image)
    guard let data = rep.representation(using: .png, properties: [:]) else {
        fail("could not encode png: \(url.path)")
    }
    do {
        try data.write(to: url, options: .atomic)
    } catch {
        fail("could not write png: \(url.path): \(error)")
    }
}

let (inputURL, outputURL, petSize) = parseArguments()
let sheet = loadSpritesheet(inputURL)
try? FileManager.default.createDirectory(at: outputURL, withIntermediateDirectories: true)
let animationsURL = outputURL.appendingPathComponent("animations", isDirectory: true)
try? FileManager.default.createDirectory(at: animationsURL, withIntermediateDirectories: true)

for frame in frames {
    let rect = CGRect(
        x: frame.column * cellWidth,
        y: frame.row * cellHeight,
        width: cellWidth,
        height: cellHeight
    )
    guard let crop = sheet.cropping(to: rect) else {
        fail("could not crop \(frame.key)")
    }
    writePNG(renderSquare(crop, size: fullSize), to: outputURL.appendingPathComponent("\(frame.file).png"))
    writePNG(renderSquare(crop, size: petSize), to: outputURL.appendingPathComponent("\(frame.file)_\(petSize).png"))
}

for animation in animations {
    for column in 0..<animation.frames {
        let rect = CGRect(
            x: column * cellWidth,
            y: animation.row * cellHeight,
            width: cellWidth,
            height: cellHeight
        )
        guard let crop = sheet.cropping(to: rect) else {
            fail("could not crop \(animation.key) frame \(column)")
        }
        writePNG(
            renderSquare(crop, size: petSize),
            to: animationsURL.appendingPathComponent("\(animation.key)_\(column)_\(petSize).png")
        )
    }
}
