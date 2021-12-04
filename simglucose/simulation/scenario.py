import logging
from collections import namedtuple
from datetime import datetime
from datetime import timedelta
import numpy as np 
from scipy.stats import truncnorm

logger = logging.getLogger(__name__)
Action = namedtuple('scenario_action', ['meal'])


class Scenario(object):
    def __init__(self, start_time):
        self.start_time = start_time

    def get_action(self, t):
        raise NotImplementedError

    def reset(self):
        raise NotImplementedError


class CustomScenario(Scenario):
    def __init__(self, start_time, scenario):
        '''
        scenario - a list of tuples (time, action), where time is a datetime or
                   timedelta or double, action is a namedtuple defined by
                   scenario.Action. When time is a timedelta, it is
                   interpreted as the time of start_time + time. Time in double
                   type is interpreted as time in timedelta with unit of hours
        '''
        Scenario.__init__(self, start_time=start_time)
        self.scenario = scenario

    def get_action(self, t):
        if not self.scenario:
            return Action(meal=0)
        else:
            times, actions = tuple(zip(*self.scenario))
            times2compare = [parseTime(time, self.start_time) for time in times]
            if t in times2compare:
                idx = times2compare.index(t)
                return Action(meal=actions[idx])
            return Action(meal=0)

    def reset(self):
        pass
    
class CustomSchedule(Scenario):
    def __init__(self, start_time, schedule):
        
        Scenario.__init__(self, start_time=start_time)
        self.schedule = schedule
    
    def get_action(self, t):
        # t must be datetime.datetime object
        delta_t = t - datetime.combine(t.date(), datetime.min.time())
        t_sec = delta_t.total_seconds()

        if t_sec < 1:
            logger.info('Creating new one day scenario ...')
            self.scenario = self.create_scenario()

        t_min = np.floor(t_sec / 60.0)

        if t_min in self.scenario['meal']['time']:
            logger.info('Time for meal!')
            idx = self.scenario['meal']['time'].index(t_min)
            return Action(meal=self.scenario['meal']['amount'][idx])
        else:
            return Action(meal=0)

    def create_scenario(self):
        scenario = {'meal': {'time': [], 'amount': []}}

        # Probability of taking each meal
        # [breakfast, snack1, lunch, snack2, dinner, snack3]            
        prob = self.schedule[0]
        time_lb = self.schedule[1] * 60
        time_ub = self.schedule[2] * 60
        time_mu = self.schedule[3]
        time_sigma = self.schedule[4]
        amount_mu = self.schedule[5]
        amount_sigma = self.schedule[6]      

        for p, tlb, tub, tbar, tsd, mbar, msd in zip(prob, time_lb, time_ub,
                                                     time_mu, time_sigma,
                                                    amount_mu, amount_sigma):
            
            if self.random_gen.rand() < p:
                tmeal = np.round(
                    truncnorm.rvs(a=(tlb - tbar) / (tsd),
                                  b=(tub - tbar) / (tsd),
                                  loc=tbar,
                                  scale=(tsd),
                                  random_state=self.random_gen))
                scenario['meal']['time'].append(tmeal)
                scenario['meal']['amount'].append(
                    max(round(self.random_gen.normal(mbar, msd)), 0))

        return scenario

    def reset(self):
        self.random_gen = np.random.RandomState(self.seed)
        self.scenario = self.create_scenario()

    @property
    def seed(self):
        return self._seed

    @seed.setter
    def seed(self, seed):
        self._seed = seed
        self.reset()


def parseTime(time, start_time):
    if isinstance(time, (int, float)):
        t = start_time + timedelta(minutes=round(time * 60.0))
    elif isinstance(time, timedelta):
        t_sec = time.total_seconds()
        t_min = round(t_sec / 60.0)
        t = start_time + timedelta(minutes=t_min)
    elif isinstance(time, datetime):
        t = time
    else:
        raise ValueError('Expect time to be int, float, timedelta, datetime')
    return t
