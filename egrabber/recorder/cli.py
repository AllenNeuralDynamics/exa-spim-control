from . import *
from ..egentl import EGenTL
from ..egrabber import *

import click
import os
import re
import signal
import sys
from datetime import datetime
from PIL import Image

# Override some of click's default behavior
class Group(click.Group):
    def get_help_option(self, ctx):
        h = super(Group, self).get_help_option(ctx)
        if h:
            h.help = 'display help and exit'
        return h
    def command(self, *args, **kwargs):
        class Command(click.Command):
            def get_help_option(self, ctx):
                h = super(Command, self).get_help_option(ctx)
                if h:
                    h.help = 'display help and exit'
                return h
        return super(Group, self).command(cls=Command, *args, **kwargs)

# Container
class Container(object):
    def __init__(self, lib=None, path=None):
        self.lib = RecorderLibrary(lib)
        self.path = os.path.abspath(path or '.')
    def open(self, mode=RECORDER_OPEN_MODE_READ, close_mode=RECORDER_CLOSE_MODE_KEEP):
        return self.lib.open_recorder(self.path, mode, close_mode=close_mode)
pass_container = click.make_pass_decorator(Container)

# Command line interface root
@click.group(cls=Group)
@click.option('--lib', default=None, type=click.Path(exists=True, dir_okay=False), hidden=True)
@click.option('-C', '--container', default='.', type=click.Path(file_okay=False), help='path to container')
@click.pass_context
def cli(ctx, lib, container):
    ctx.obj = Container(lib, container)

# status
@cli.command(short_help='show basic information')
@pass_container
def status(container):
    '''Show information related to the container.'''
    def show_size(n):
        if n > 1e9:
            return '%i (%.1f GB)' % (n, n / 1e9)
        elif n > 1e6:
            return '%i (%.1f MB)' % (n, n / 1e6)
        else:
            return '%i (%.1f kB)' % (n, n / 1e3)
    with container.open() as recorder:
        click.echo('Container path:                  %s' % container.path)
        click.echo('Container size:                  %s' % show_size(recorder.get(RECORDER_PARAMETER_CONTAINER_SIZE)))
        click.echo('Number of chapters in container: %i' % recorder.get(RECORDER_PARAMETER_CHAPTER_COUNT))
        click.echo('Number of records in container:  %i' % recorder.get(RECORDER_PARAMETER_RECORD_COUNT))
        click.echo('Remaining space in container:    %s' % show_size(recorder.get(RECORDER_PARAMETER_REMAINING_SPACE_IN_CONTAINER)))
        click.echo('Remaining space on device:       %s' % show_size(recorder.get(RECORDER_PARAMETER_REMAINING_SPACE_ON_DEVICE)))
        click.echo('Buffer optimal alignment:        %i' % recorder.get(RECORDER_PARAMETER_BUFFER_OPTIMAL_ALIGNMENT))
        click.echo('Database version:                %s' % recorder.get(RECORDER_PARAMETER_DATABASE_VERSION))
        click.echo('eGrabber Recorder version:       %s' % recorder.get(RECORDER_PARAMETER_VERSION))

def asUTC(utc):
    d = datetime.utcfromtimestamp(utc)
    return d.strftime('%Y-%m-%d %H:%M:%S.%f UTC')

# log
@cli.command(short_help='show container records')
@pass_container
def log(container):
    '''Show information related to records written in the container.'''
    with container.open() as recorder:
        record_count = recorder.get(RECORDER_PARAMETER_RECORD_COUNT)
        def show_info():
            yield 'Chapters\n'
            yield '--------\n'
            for index in range(len(recorder.chapters)):
                chapter = recorder.chapters[index]
                lines = [] if index == 0 else ['\n']
                lines += ['  index:             %i\n' % index]
                if chapter:
                    lines += ['  name:              %s\n' % chapter.name]
                    lines += ['  user info:         %s\n' % chapter.user_info]
                    lines += ['  base record index: %i\n' % chapter.base_record_index]
                    lines += ['  number of records: %i\n' % chapter.record_count]
                    lines += ['  timestamp:         %.9f\n' % (chapter.timestamp_ns * 1e-9)]
                    lines += ['  utc:               %.9f (%s)\n' % (chapter.utc_ns * 1e-9, asUTC(chapter.utc_ns * 1e-9))]
                else:
                    lines += ['  <not available>\n']
                yield ''.join(lines)
            yield '\n'
            yield 'Records\n'
            yield '-------\n'
            for index in range(record_count):
                recorder.set(RECORDER_PARAMETER_RECORD_INDEX, index)
                info = recorder.read_info()
                lines = [] if index == 0 else ['\n']
                lines += ['  index:          %i\n' % index]
                lines += ['  size:           %i\n' % info.size]
                lines += ['  pitch:          %i\n' % info.pitch]
                lines += ['  width:          %i\n' % info.width]
                lines += ['  height:         %i\n' % info.height]
                lines += ['  pixel format:   0x%08x (%s)\n' % (info.pixelformat, get_pixel_format(info.pixelformat))]
                lines += ['  part count:     %i\n' % info.partCount]
                lines += ['  timestamp:      %.9f\n' % (info.timestamp * 1e-9)]
                lines += ['  utc:            %.9f (%s)\n' % (info.utc * 1e-9, asUTC(info.utc * 1e-9))]
                lines += ['  user data:      %i\n' % info.userdata]
                lines += ['  chapter index:  %i\n' % info.chapterIndex]
                yield ''.join(lines)
        click.echo_via_pager(show_info)

# export
@cli.command(short_help='export images')
@click.option('-o', '--output', default='@n.tiff', type=click.Path(), show_default=True,
              help='destination path (`@n` patterns will be replaced by `record index - start index`)')
@click.option('-i', '--index',  default=0,         type=click.INT,    show_default=True,
              help='start index relative to the beginning of the container (or chapter if defined); '
                   'negative values are relative to the end of the container (or chapter if defined)')
@click.option('-n', '--count',  default=None,      type=click.INT,
              help='number of records to export')
@click.option('-f', '--format', default=None,      metavar='FORMAT',
              help='export pixel format')
@click.option('-c', '--chapter', default=None,     metavar='CHAPTER',
              help='start from a specified chapter (identified by name or index); '
                   'the start index (-i) becomes relative to that chapter')
@pass_container
def export(container, output, index, count, format, chapter):
    '''Export images from the container.
    '''
    with container.open() as recorder:
        if chapter is not None:
            try:
                found_chapter = recorder.chapters[int(chapter)]
            except ValueError:
                found_chapter = recorder.find_chapter_by_name(chapter)
            except Exception:
                found_chapter = None
            if not found_chapter:
                raise click.ClickException('Chapter not found: %s' % chapter)
            record_count = found_chapter.record_count
        else:
            found_chapter = None
            record_count = recorder.get(RECORDER_PARAMETER_RECORD_COUNT)
        if not index:
            index = 0;
        if index < 0 and record_count + index >= 0:
            index = record_count + index
        if index < 0 or index >= record_count:
            raise click.ClickException('Index out of bounds')
        if count is None:
            count = record_count - index
        if found_chapter:
            index += found_chapter.base_record_index
        recorder.set(RECORDER_PARAMETER_RECORD_INDEX, index)
        if looks_like_dir(output):
            output = os.path.join(output, '@n.tiff')
        if format is None:
            format = 0
        else:
            try:
                format = int(format)
            except ValueError:
                format = get_pixel_format_value(format)
        makedirs(os.path.dirname(output))
        with click.progressbar(length=count, label='Exporting images') as bar:
            bar.already_exported = 0 # using bar.pos would be simpler, but it's not part of the documented API
            def on_progress(progress):
                index = progress.index + 1
                inc, bar.already_exported = index - bar.already_exported, index
                bar.update(inc)
            h = signal.signal(signal.SIGINT, lambda n, f: recorder.abort()) # ok because we're on the main thread
            try:
                recorder.export(output, count, export_pixel_format=format, on_progress=on_progress)
            finally:
                signal.signal(signal.SIGINT, h)

def read_size(s):
    unit = { '': 1, 'B': 1, 'KB': 1000, 'MB': 1000*1000,
             'GB': 1000*1000*1000, 'TB': 1000*1000*1000*1000 }
    m = re.match('^(\d+)(B|KB|MB|GB|TB)?$', ''.join(s.split()), re.IGNORECASE)
    if m:
        size = int(m[1])
        if m[2]:
            size *= unit[m[2].upper()]
        return size
    else:
        raise click.ClickException('Invalid size: %s' % s)

def makedirs(path):
    try:
        os.makedirs(path)
    except Exception:
        pass

def looks_like_dir(path):
    if os.path.isdir(path):
        return True
    _, tail = os.path.split(path)
    if not tail:
        return True
    _, ext = os.path.splitext(tail)
    if not ext:
        return True
    return False

# create
@cli.command(short_help='create a new container')
@click.option('--size', default='0', metavar='SIZE', show_default=True,
              help='size of the new container (SIZE can be suffixed by one of the following: B, kB, MB, GB, TB)')
@pass_container
def create(container, size):
    '''Create a new container.'''
    try:
        with container.open():
            pass
        raise click.ClickException('A container already exists in %s' % container.path)
    except RecorderError as err:
        pass
    makedirs(container.path)
    with container.open(RECORDER_OPEN_MODE_WRITE, RECORDER_CLOSE_MODE_KEEP) as recorder:
        size = read_size(size)
        recorder.set(RECORDER_PARAMETER_CONTAINER_SIZE, size)

# resize
@cli.command(short_help='resize the container')
@click.option('--size', default=None, metavar='SIZE',
              help='new container size (SIZE can be suffixed by one of the following: B, kB, MB, GB, TB)')
@click.option('--dont-trim-chapters', default=False, flag_value=True,
              help='keep trailing empty chapters')
@pass_container
def resize(container, size, dont_trim_chapters):
    '''Resize the container.

       If --size is omitted, the container is trimmed (i.e., the container is
       reduced to the smallest size that fits the container contents).
    '''
    close_mode = RECORDER_CLOSE_MODE_TRIM if size is None else RECORDER_CLOSE_MODE_KEEP
    close_mode += RECORDER_CLOSE_MODE_DONT_TRIM_CHAPTERS if dont_trim_chapters else 0
    with container.open(RECORDER_OPEN_MODE_APPEND, close_mode) as recorder:
        if size is not None:
            size = read_size(size)
            recorder.set(RECORDER_PARAMETER_CONTAINER_SIZE, size)

# record
@cli.command(short_help='record images')
@click.option('--cti',           default=None, metavar='PATH',    help='path to the GenTL producer library')
@click.option('--if', 'iface',   default=0,    metavar='ID',      help='interface id',   show_default=True)
@click.option('--dev',           default=0,    metavar='ID',      help='device id',      show_default=True)
@click.option('--ds',            default=0,    metavar='ID',      help='data stream id', show_default=True)
@click.option('-n', '--count',   default=None, type=click.INT,    help='number of images to record')
@click.option('--buffers',       default=3,    type=click.INT,    help='number of buffers to use', show_default=True)
@click.option('--setup',         default=None, metavar='SCRIPT',  help='script to execute before starting the data stream')
@click.option('-c', '--chapter', default='',   metavar='CHAPTER', help='optional chapter name')
@click.option('--chapter-info',  default='',   metavar='INFO',    help='optional chapter user information')
@click.option('--trim-container',     default=False, flag_value=True, help='trim the container size when closing the recorder')
@click.option('--dont-trim-chapters', default=False, flag_value=True, help='keep trailing empty chapters')
@pass_container
def record(container, cti, iface, dev, ds, count, buffers, setup, chapter, chapter_info, trim_container, dont_trim_chapters):
    '''Record images in the container.'''
    close_mode = RECORDER_CLOSE_MODE_TRIM if trim_container else RECORDER_CLOSE_MODE_KEEP
    close_mode += RECORDER_CLOSE_MODE_DONT_TRIM_CHAPTERS if dont_trim_chapters else 0
    with container.open(RECORDER_OPEN_MODE_APPEND, close_mode) as recorder:
        gentl = EGenTL(cti)
        grabber = EGrabber(gentl, interface=iface, device=dev, data_stream=ds)
        alignment = recorder.get(RECORDER_PARAMETER_BUFFER_OPTIMAL_ALIGNMENT)
        grabber.stream.set('BufferAllocationAlignmentControl', 'Enable')
        grabber.stream.set('BufferAllocationAlignment', alignment)
        if setup:
            grabber.run_script(setup)
        grabber.realloc_buffers(buffers)
        if count is None:
            remaining_space = recorder.get(RECORDER_PARAMETER_REMAINING_SPACE_IN_CONTAINER)
            count = int(remaining_space / grabber.get_payload_size())
            if not count:
                raise DataFileFull
        if count:
            grabber.start(count)
        recorder.start_chapter(chapter, chapter_info)
        with click.progressbar(range(count), label='Recording images') as bar:
            for n in bar:
                with Buffer(grabber) as buffer:
                    info = RECORDER_BUFFER_INFO()
                    info.size = buffer.get_info(BUFFER_INFO_SIZE, INFO_DATATYPE_SIZET)
                    info.pitch = buffer.get_info(BUFFER_INFO_CUSTOM_LINE_PITCH, INFO_DATATYPE_SIZET)
                    info.width = buffer.get_info(BUFFER_INFO_WIDTH, INFO_DATATYPE_SIZET)
                    info.height = buffer.get_info(BUFFER_INFO_DELIVERED_IMAGEHEIGHT, INFO_DATATYPE_SIZET)
                    info.pixelformat = buffer.get_info(BUFFER_INFO_PIXELFORMAT, INFO_DATATYPE_UINT64)
                    info.partCount = buffer.get_info(BUFFER_INFO_CUSTOM_NUM_PARTS, INFO_DATATYPE_SIZET)
                    info.timestamp = buffer.get_info(BUFFER_INFO_TIMESTAMP_NS, INFO_DATATYPE_UINT64)
                    info.userdata = 0
                    base = buffer.get_info(BUFFER_INFO_BASE, INFO_DATATYPE_PTR)
                    recorder.write(info, to_cchar_array(base, info.size))

gentl = None
def get_pixel_format(pf):
    global gentl
    if not gentl:
        gentl = EGenTL()
    try:
        return gentl.image_get_pixel_format(pf)
    except Exception:
        return 'unknown'
def get_pixel_format_value(pf):
    global gentl
    if not gentl:
        gentl = EGenTL()
    return gentl.image_get_pixel_format_value(pf)

def main():
    try:
        cli(prog_name='python -m egrabber.recorder', help_option_names=['-h', '--help'])
    except RecorderError as err:
        click.echo('Error: %s' % err)
        sys.exit(1)
    except Exception as err:
        click.echo('Exception: %s' % err)
        sys.exit(1)
