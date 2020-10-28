#! /usr/bin/env python

"""
NOTE: this is/should be superseded by the `toasty transform` CLI command
"""

import argparse
from astropy import visualization as viz
import multiprocessing as mp
import numpy as np
from toasty.image import ImageMode, Image
from toasty.pyramid import PyramidIO, depth2tiles, generate_pos, Pos
from tqdm import tqdm


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--depth',
        type = int,
        default = 3,
        metavar = 'DEPTH',
        help = 'How deep to start the conversion',
    )
    parser.add_argument(
        '--parallel', '-p',
        type = int,
        default = 2,
        metavar = 'P',
        help = 'Parallelism',
    )
    parser.add_argument(
        'pyramid_dir',
        metavar = 'DIR',
        help = 'The directory containg the tile pyramid to cascade',
    )

    settings = parser.parse_args()

    pio = PyramidIO(settings.pyramid_dir)

    # Compute mapping info from level 0 tile
    # Different exposures in the sims have fairly different characteristics.
    # For the purposes of this demo we try to Gaussian normalize

    img = pio.read_image(Pos(0, 0, 0), ImageMode.F32)
    arr = img.asarray()
    arr = arr[np.isfinite(arr)]

    pcts = np.percentile(arr, [16, 50, 84])
    offset = pcts[1]
    scale = 0.5 * (pcts[2] - pcts[0])
    llim = offset - 2 * scale
    ulim = offset + 50 * scale

    transform = viz.SqrtStretch() + viz.ManualInterval(llim, ulim)

    # Start up the workers

    queue = mp.Queue(maxsize = 16 * settings.parallel)
    workers = []

    for _ in range(settings.parallel):
        w = mp.Process(target=cmap_worker, args=(queue, pio, transform))
        w.daemon = True
        w.start()
        workers.append(w)

    # Send out them tiles

    with tqdm(total=depth2tiles(settings.depth)) as progress:
        for pos in generate_pos(settings.depth):
              queue.put(pos)
              progress.update(1)

        queue.close()

        for w in workers:
            w.join()


def cmap_worker(queue, pio, transform):
    """
    Do the colormapping.
    """
    from queue import Empty

    buf = np.empty((256, 256, 4), dtype=np.uint8)

    while True:
        try:
            pos = queue.get(True, timeout=1)
        except (OSError, ValueError, Empty):
            # OSError or ValueError => queue closed. This signal seems not to
            # cross multiprocess lines, though.
            break

        img = pio.read_image(pos, ImageMode.F32)
        if img is None:
            continue

        mapped = transform(img.asarray())
        valid = np.isfinite(mapped)
        mapped[~valid] = 0
        mapped = np.clip(mapped * 255, 0, 255).astype(np.uint8)
        buf[...,:3] = mapped.reshape((256, 256, 1))
        buf[...,3] = 255 * valid

        rgb = Image.from_array(ImageMode.RGBA, buf)
        pio.write_image(pos, rgb)


if __name__ == '__main__':
    main()
