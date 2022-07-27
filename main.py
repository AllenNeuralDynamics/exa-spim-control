import napari
from UserInterface import UserInterface

def main():

    viewer = napari.Viewer(title = 'exaSPIM control', ndisplay = 2, axis_labels=('x','y'))
    viewer.theme = 'dark'
    
    gui = UserInterface()
    gui._set_viewer(viewer)
    gui._startup()

    worker_live = gui._acquire_live()
    worker_live.yielded.connect(gui._update_display)
    gui._set_worker_live(worker_live)

    worker_record = gui._acquire_record()
    worker_record.yielded.connect(gui._update_display)
    gui._set_worker_record(worker_record)

    viewer.window.add_dock_widget(gui, area='right', name='Settings')
    napari.run(max_loop_level=2)

    worker_live.quit()
    worker_record.quit()

if __name__ == "__main__":
    main()