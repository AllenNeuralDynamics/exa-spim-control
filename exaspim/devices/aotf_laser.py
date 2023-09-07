
class test:
    def __init__(self):
        self.test = 'test'


class AOTFLaser:

    def __init__(self, wl, cfg):

      self.wl = wl
      self.cfg = cfg
      print('cfg', self.cfg)
    def get_setpoint(self):
        return self.cfg.get_channel_ao_voltage(self.wl)*100

    def set_setpoint(self, value):
        self.cfg.set_channel_ao_voltage(str(self.wl), value / 100)

    def get_max_setpoint(self):
        return 1000

    def enable(self):
        pass
    def disable(self):
        pass