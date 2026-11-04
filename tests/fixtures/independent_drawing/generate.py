"""自绘试件，非学生资料。解析依据：36×24 mm 倒角板，两个梯形透孔，厚 3 mm。

PDF 使用 4 pt/mm；错误变体把左孔一个顶点移动 2 mm。无人工抄录图纸面积。
纯标准库写最小 PDF，避免为测试增加生产依赖。
"""
from pathlib import Path

OUTER = [(-16, -12), (16, -12), (18, -10), (18, 10), (16, 12), (-16, 12), (-18, 10), (-18, -10)]
HOLES = [[(-13, -6), (-5, -4), (-5, 4), (-13, 6)], [(5, -4), (13, -6), (13, 6), (5, 4)]]


def loops(wrong=False):
    result = [[list(p) for p in loop] for loop in [OUTER, *HOLES]]
    if wrong:
        result[1][1][1] -= 2
    return result


def make_pdf(path):
    commands = []
    def line(a, b):
        commands.append(f'{160+4*a[0]} {160+4*a[1]} m {160+4*b[0]} {160+4*b[1]} l S')
    commands.append('0.7 w')
    for loop in loops():
        for a, b in zip(loop, loop[1:]+loop[:1]):
            line(a, b)
    commands.append('0.35 w')
    for a, b in [((-18, 10), (-18, 20)), ((18, 10), (18, 20)), ((-18, 18), (18, 18)),
                 ((16, -12), (26, -12)), ((16, 12), (26, 12)), ((24, -12), (24, 12))]:
        line(a, b)
    commands.extend(['BT /F1 6 Tf 156.664 233.242 Td (36) Tj ET',
                     'BT /F1 6 Tf 0 1 -1 0 254.758 156.664 Tm (24) Tj ET'])
    stream = ('\n'.join(commands)+'\n').encode('ascii')
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>', b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
               b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 320 320] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
               b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
               f'<< /Length {len(stream)} >>\nstream\n'.encode()+stream+b'endstream']
    data, offsets = b'%PDF-1.4\n', []
    for i, obj in enumerate(objects, 1):
        offsets.append(len(data))
        data += f'{i} 0 obj\n'.encode()+obj+b'\nendobj\n'
    start = len(data)
    data += b'xref\n0 6\n0000000000 65535 f \n'+b''.join(f'{n:010} 00000 n \n'.encode() for n in offsets)
    data += f'trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n'.encode()
    Path(path).write_bytes(data)


if __name__ == '__main__':
    make_pdf(Path(__file__).with_name('plate.pdf'))
