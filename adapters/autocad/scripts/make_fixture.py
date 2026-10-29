#!/usr/bin/env python3
"""Create a synthetic native-entity DXF for integration checks, not a course drawing."""
from pathlib import Path
import argparse
import ezdxf


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit('Refusing to overwrite an existing fixture.')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    doc = ezdxf.new('R2018', setup=True)
    doc.units = ezdxf.units.MM
    model = doc.modelspace()
    model.add_line((0, 0), (100, 0))
    model.add_lwpolyline([(0, 10), (100, 10), (100, 30), (0, 30)], close=True)
    model.add_circle((125, 20), 10)
    model.add_arc((155, 20), 10, 0, 90)
    model.add_text('GONGKE_NATIVE_FIXTURE', dxfattribs={'insert': (0, 45), 'height': 3})
    model.add_mtext('Synthetic integration fixture\\PNot an engineering release', dxfattribs={'insert': (0, 65), 'char_height': 3, 'width': 100})
    dimension = model.add_linear_dim(base=(0, -15), p1=(0, 0), p2=(100, 0), angle=0,
                                     override={'dimtxt': 3, 'dimasz': 2, 'dimtad': 1})
    dimension.render()
    doc.saveas(args.output)
    reread = ezdxf.readfile(args.output)
    counts = {kind: len(reread.modelspace().query(kind)) for kind in ('LINE', 'LWPOLYLINE', 'CIRCLE', 'ARC', 'TEXT', 'MTEXT', 'DIMENSION')}
    assert all(counts.values()), counts
    print({'path': str(args.output.resolve()), 'synthetic': True, 'units': 'mm', 'entity_counts': counts})


if __name__ == '__main__':
    main()
