#! /usr/bin/env python

"""
NOTE: this requires as-yet-unreleased `reproject` containing the pull request
https://github.com/astropy/reproject/pull/242
"""

import argparse
import numpy as np
import os.path
from reproject import reproject_interp
from toasty.builder import Builder
from toasty.image import ImageMode
from toasty.merge import averaging_merger, cascade_images
from toasty.multi_wcs import MultiWcsProcessor, make_lsst_directory_loader_generator
from toasty.pyramid import PyramidIO

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--parallelism', '-p',
        type = int,
        metavar = 'N',
        help = 'The parallelism',
    )
    parser.add_argument(
        'fits_dir',
        metavar = 'DIR',
        help = 'The directory containing the input FITS files',
    )
    parser.add_argument(
        'pyramid_dir',
        metavar = 'DIR',
        help = 'The directory containing the output tile pyramid',
    )

    settings = parser.parse_args()

    # Do the damn thing

    pio = PyramidIO(settings.pyramid_dir)
    builder = Builder(pio)
    loadgen = make_lsst_directory_loader_generator(settings.fits_dir, unit='adu')
    proc = MultiWcsProcessor(loadgen)

    print('Computing common coordinate system ...')
    proc.compute_global_pixelization()
    print('...', len(proc._descs), 'input segments')

    print('Tiling base layer ...')
    proc.tile(pio, reproject_interp, cli_progress=True, parallel=settings.parallelism)

    print('Generating index_rel.wtml ...')
    builder.make_placeholder_thumbnail()
    proc._tiling.apply_to_imageset(builder.imgset)
    builder.imgset.file_type = '.png'
    builder.imgset.url = pio.get_path_scheme() + '.png'
    builder.apply_wcs_info(proc._combined_wcs, proc._combined_shape[1], proc._combined_shape[0])
    builder.set_name(os.path.basename(settings.fits_dir))
    builder.write_index_rel_wtml()

    print('Cascading science data ...')
    cascade_images(
        pio,
        ImageMode.F32,
        proc._tiling._tile_levels,
        averaging_merger,
        cli_progress=True,
        parallel=settings.parallelism,
    )


if __name__ == '__main__':
    main()
