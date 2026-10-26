import AppKit
// sheet out.png in1 in2 …: 2 columns of 640x360 tiles, in reading order
let a = CommandLine.arguments
guard a.count > 2 else { FileHandle.standardError.write("usage: sheet out.png in…\n".data(using: .utf8)!); exit(2) }
let n = a.count - 2, cols = 2, w = 640, h = 360, rows = (n + 1) / 2
let img = NSImage(size: NSSize(width: cols * w, height: rows * h))
img.lockFocus()
for i in 0..<n { if let im = NSImage(contentsOfFile: a[i + 2]) { im.draw(in: NSRect(x: (i % cols) * w, y: (rows - 1 - i / cols) * h, width: w, height: h)) } }
img.unlockFocus()
let rep = NSBitmapImageRep(data: img.tiffRepresentation!)!
try! rep.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: a[1]))
