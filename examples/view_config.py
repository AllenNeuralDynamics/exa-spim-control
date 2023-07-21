from exaspim.exaspim_config import ExaspimConfig
import pprint


cfg = ExaspimConfig("C:\\Users\\Administrator\\Documents\\Github\\exa-spim-control\\bin\\config.toml")
#pprint.pprint(cfg.channel_specs)
print(cfg.get_etl_buffer_time('561'))