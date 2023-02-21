"""Downsample Operation implemented on the GPU to shrink images for display."""

from gputools import OCLProgram, OCLArray, get_device


class DownSample:

    def __init__(self):
        self.downsample_factor = 2
        self.downsample_levels = 5

        # opencl kernel
        self.kernel = """
        __kernel void downsample2d(__global short * input,
                                   __global short * output){
          int i = get_global_id(0);
          int j = get_global_id(1);
          int Nx = get_global_size(0);
          int Ny = get_global_size(1);
          int res = 0; 

          for (int m = 0; m < BLOCK; ++m) 
             for (int n = 0; n < BLOCK; ++n) 
                  res+=input[BLOCK*Nx*(BLOCK*j+m)+BLOCK*i+n];
          output[Nx*j+i] = (short)(res/BLOCK/BLOCK);
        }
        """

        self.prog = OCLProgram(src_str=self.kernel,
                               build_options=['-D', f'BLOCK={self.downsample_factor}'])

    def compute(self, image):
        pyramid = []
        pyramid.append(image)
        for level in range(0, self.downsample_levels):
            x_g = OCLArray.from_array(image)
            y_g = OCLArray.empty(tuple(s // self.downsample_factor for s in image.shape), image.dtype)
            self.prog.run_kernel(f'downsample2d', y_g.shape[::-1],
                                 None, x_g.data, y_g.data)
            image = y_g.get()
            pyramid.append(image)

        return pyramid
