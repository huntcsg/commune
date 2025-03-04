import commune as c
from typing import *


class Access(c.Module):
    sync_time = 0
    timescale_map  = {'sec': 1, 'min': 60, 'hour': 3600, 'day': 86400}

    def __init__(self, 
                module : Union[c.Module, str], # the module or any python object
                network: str =  'main', # mainnet
                netuid: int = 0, # subnet id
                sync_interval: int =  30, #  1000 seconds per sync with the network
                timescale:str =  'min', # 'sec', 'min', 'hour', 'day'
                stake2rate: int =  100,  # 1 call per every N tokens staked per timescale
                rate: int =  1,  # 1 call per timescale
                base_rate: int =  0,# base level of calls per timescale (free calls) per account
                fn2rate: dict =  {}, # function name to rate map, this overrides the default rate,
                role2rate: dict =  {'user': 10, 'public': 1}, # role to rate map, this overrides the default rate,
                state_path = f'state_path', # the path to the state
                **kwargs):
        
        config = self.set_config(kwargs=locals())
        self.module = module
        self.user_info = {}
        self.stakes = {}
        self.state_path = state_path
        self.role2rate = role2rate
        module.client_access = False
        self.user_module = c.module('user')()
        c.thread(self.sync_loop_thread)
        
    def sync_loop_thread(self):
        while True:
            self.sync()

    def sync(self):

        try:
            # if the sync time is greater than the sync interval, we need to sync
            state = self.get(self.state_path, default={})

            time_since_sync = c.time() - state.get('sync_time', 0)
            if time_since_sync > self.config.sync_interval:
                self.subspace = c.module('subspace')(network=self.config.network)
                state['stakes'] = self.subspace.stakes(fmt='j', netuid=self.config.netuid)
                state['sync_time'] = c.time()

            self.stakes = state['stakes']
            until_sync = self.config.sync_interval - time_since_sync

            response = {  'until_sync': until_sync,
                          'time_since_sync': time_since_sync
                          }
            return response
        except Exception as e:
            e = c.detailed_error(e)
            c.print(e)
            response = {'error': e}
        return response

    def verify(self, input:dict) -> dict:
        address = input['address']
        user_info = self.user_info.get(address, {'last_time_called':0 , 'requests': 0})
        stake = self.stakes.get(address, 0)
        fn = input.get('fn')

        if self.user_module.is_admin(address) or self.module.key.ss58_address == address:
            rate_limit = 10e42

        elif self.user_module.is_user(address):
            rate_limit = self.role2rate.get('user', 1)
        else:
            assert fn in self.module.whitelist or fn in c.helper_whitelist, f"Function {fn} not in whitelist"
            assert fn not in self.module.blacklist, f"Function {fn} is blacklisted" 
            rate_limit = (stake / self.config.stake2rate) # convert the stake to a rate
            rate_limit = rate_limit + self.config.base_rate # add the base rate
            rate_limit = rate_limit * self.config.rate # multiply by the rate

        # check if the user has exceeded the rate limit
        time_since_called = c.time() - user_info['last_time_called']
        seconds_in_period = self.timescale_map[self.config.timescale]
        if time_since_called > seconds_in_period:
            user_info['requests'] = 0

        passed = bool(user_info['requests'] <= rate_limit)
        
        # update the user info
        user_info['rate_limit'] = rate_limit
        user_info['stake'] = stake
        user_info['seconds_in_period'] = seconds_in_period
        user_info['passed'] = passed
        user_info['time_since_called'] = time_since_called
        self.user_info[address] = user_info

        assert  passed,  f"Rate limit too high (calls per second) {user_info}"

        user_info['last_time_called'] = c.time()
        user_info['requests'] +=  1
        # check the rate limit
        return user_info


    @classmethod
    def test(cls, key='vali::fam', base_rate=2):
        
        module = cls(module=c.module('module')(),  base_rate=base_rate)
        key = c.get_key(key)

        for i in range(base_rate*3):
            c.sleep(0.1)
            try:
                c.print(module.verify(input={'address': key.ss58_address, 'fn': 'info'}))
            except Exception as e:
                c.print(e)
                assert i > base_rate

            

            
