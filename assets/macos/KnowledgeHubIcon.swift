// Original Knowledge Hub / Lexicon icon. No font, emoji or borrowed artwork.
// Render: swift KnowledgeHubIcon.swift /path/to/KnowledgeHub.iconset
// Package: iconutil -c icns /path/to/KnowledgeHub.iconset -o KnowledgeHub.icns
import AppKit

let output = URL(fileURLWithPath: CommandLine.arguments[1], isDirectory: true)
try FileManager.default.createDirectory(at: output, withIntermediateDirectories: true)
func color(_ r: CGFloat, _ g: CGFloat, _ b: CGFloat) -> NSColor {
    NSColor(srgbRed: r / 255, green: g / 255, blue: b / 255, alpha: 1)
}
let ink = color(100, 38, 49)
let ivory = color(247, 241, 228)
for points in [16, 32, 128, 256, 512] {
    for scale in [1, 2] {
        let pixels = points * scale
        let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: pixels,
            pixelsHigh: pixels, bitsPerSample: 8, samplesPerPixel: 4,
            hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB,
            bytesPerRow: 0, bitsPerPixel: 0)!
        NSGraphicsContext.saveGraphicsState()
        NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: rep)
        let context = NSGraphicsContext.current!.cgContext
        context.scaleBy(x: CGFloat(pixels) / 1024, y: CGFloat(pixels) / 1024)
        context.setAllowsAntialiasing(true)
        // Inset native silhouette, quietly dimensional ivory ceramic field.
        let tile = NSBezierPath(roundedRect: NSRect(x: 64, y: 64, width: 896,
            height: 896), xRadius: 196, yRadius: 196)
        NSGraphicsContext.saveGraphicsState()
        let shadow = NSShadow()
        shadow.shadowColor = NSColor.black.withAlphaComponent(0.20)
        shadow.shadowOffset = NSSize(width: 0, height: -14)
        shadow.shadowBlurRadius = 22
        shadow.set()
        ivory.setFill(); tile.fill()
        NSGraphicsContext.restoreGraphicsState()
        color(223, 212, 192).setStroke(); tile.lineWidth = 4; tile.stroke()
        // Open book: two generous pages, a decisive central gutter.
        let book = NSBezierPath()
        book.move(to: NSPoint(x: 220, y: 292))
        book.line(to: NSPoint(x: 220, y: 726))
        book.curve(to: NSPoint(x: 500, y: 670), controlPoint1: NSPoint(x: 327, y: 758), controlPoint2: NSPoint(x: 420, y: 726))
        book.line(to: NSPoint(x: 500, y: 258))
        book.curve(to: NSPoint(x: 220, y: 292), controlPoint1: NSPoint(x: 411, y: 318), controlPoint2: NSPoint(x: 318, y: 323))
        book.close()
        ink.setFill(); book.fill()
        var mirror = AffineTransform()
        mirror.translate(x: 1024, y: 0); mirror.scale(x: -1, y: 1)
        let right = book.copy() as! NSBezierPath
        right.transform(using: mirror); right.fill()
        // Compact slots omit fine rules; the book silhouette carries identity.
        if points >= 32 {
            ivory.withAlphaComponent(0.78).setStroke()
            for y: CGFloat in [558, 466] {
                let rule = NSBezierPath()
                rule.move(to: NSPoint(x: 290, y: y + 26))
                rule.curve(to: NSPoint(x: 432, y: y), controlPoint1: NSPoint(x: 346, y: y + 34), controlPoint2: NSPoint(x: 390, y: y + 20))
                rule.lineWidth = 16; rule.lineCapStyle = .round; rule.stroke()
                let other = rule.copy() as! NSBezierPath
                other.transform(using: mirror); other.stroke()
            }
        }
        // Oxblood ribbon creates an asymmetric, memorable reading cue.
        if points >= 32 {
            let ribbon = NSBezierPath()
            ribbon.move(to: NSPoint(x: 690, y: 731))
            ribbon.line(to: NSPoint(x: 690, y: 589))
            ribbon.line(to: NSPoint(x: 720, y: 610))
            ribbon.line(to: NSPoint(x: 750, y: 589))
            ribbon.line(to: NSPoint(x: 750, y: 737))
            ribbon.close()
            color(200, 157, 105).setFill(); ribbon.fill()
        }
        NSGraphicsContext.restoreGraphicsState()
        let suffix = scale == 2 ? "@2x" : ""
        let file = output.appendingPathComponent("icon_\(points)x\(points)\(suffix).png")
        try rep.representation(using: .png, properties: [:])!.write(to: file)
    }
}
