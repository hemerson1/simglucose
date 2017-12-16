from rllab.envs.base import Env
from rllab.envs.base import Step
from rllab.spaces import Box
import numpy as np
from simglucose.patient.t1dpatient import Action
from simglucose.analysis.risk import risk_index
import pandas as pd
from datetime import datetime
from datetime import timedelta
import logging
import matplotlib.dates as mdates
from collections import namedtuple

Observation = namedtuple('Observation', ['CHO', 'CGM'])
logger = logging.getLogger(__name__)


class T1DSimEnv(Env):
    def __init__(self,
                 patient,
                 sensor,
                 pump,
                 scenario,
                 start_time=None,
                 sample_time=None):

        self.patient = patient
        self.sensor = sensor
        self.pump = pump
        self.scenario = scenario

        if sample_time is None:
            sample_time = self.sensor.sample_time
        if (not float(sample_time).is_integer()) or (sample_time <= 0):
            raise ValueError('Expect sample_time to be positive integer.')
        self.sample_time = sample_time

        if start_time is None:
            now = datetime.now()
            start_time = datetime.combine(now.date(), datetime.min.time())
        self.start_time = start_time

        # Initial Recording
        BG = self.patient.observation.Gsub
        horizon = 0
        LBGI, HBGI, risk = risk_index([BG], horizon)
        CGM = self.sensor.measure(self.patient)
        self.time_hist = [self.start_time]
        self.BG_hist = [BG]
        self.CGM_hist = [CGM]
        self.risk_hist = [risk]
        self.LBGI_hist = [LBGI]
        self.HBGI_hist = [HBGI]
        self.CHO_hist = []
        self.insulin_hist = []

    @property
    def time(self):
        return self.start_time + timedelta(minutes=self.patient.t)

    def mini_step(self, action):
        # current action
        patient_action = self.scenario.get_action(self.time)
        basal = self.pump.basal(action.basal)
        bolus = self.pump.bolus(action.bolus)
        insulin = basal + bolus
        CHO = patient_action.meal
        patient_mdl_act = Action(insulin=insulin, CHO=CHO)

        # State update
        # logger.info('Updating patient states ...')
        self.patient.step(patient_mdl_act)

        # next observation
        BG = self.patient.observation.Gsub
        CGM = self.sensor.measure(self.patient)

        return CHO, insulin, BG, CGM

    def step(self, action):
        '''
        action is a namedtuple with keys: basal, bolus
        '''
        CHO = 0.0
        insulin = 0.0
        BG = 0.0
        CGM = 0.0

        for _ in range(int(self.sample_time)):
            # Compute moving average as the sample measurements
            tmp_CHO, tmp_insulin, tmp_BG, tmp_CGM = self.mini_step(action)
            CHO += tmp_CHO / self.sample_time
            insulin += tmp_insulin / self.sample_time
            BG += tmp_BG / self.sample_time
            CGM += tmp_CGM / self.sample_time

        # Compute risk index
        horizon = 0
        LBGI, HBGI, risk = risk_index([BG], horizon)

        # Record current action
        self.CHO_hist.append(CHO)
        self.insulin_hist.append(insulin)

        # Record next observation
        self.time_hist.append(self.time)
        self.BG_hist.append(BG)
        self.CGM_hist.append(CGM)
        self.risk_hist.append(risk)
        self.LBGI_hist.append(LBGI)
        self.HBGI_hist.append(HBGI)

        # Compute reward, and decide whether game is over
        reward = - np.log(risk)
        done = BG < 70 or BG > 350
        obs = Observation(CHO=CHO, CGM=CGM)
        return Step(observation=obs, reward=reward, done=done)

    def reset(self):
        self.patient.reset()
        self.sensor.reset()
        self.pump.reset()
        self.scenario.reset()

    @property
    def action_space(self):
        ub = self.pump._params['max_basal'] + self.pump._params['max_bolus']
        return Box(low=0, high=ub, shape=(1,))

    @property
    def observation_space(self):
        return Box(low=0, high=np.inf, shape=(1,))

    def render(self, axes, lines):
        logger.info('Rendering ...')

        lines[0].set_xdata(self.time_hist)
        lines[0].set_ydata(self.BG_hist)

        lines[1].set_xdata(self.time_hist)
        lines[1].set_ydata(self.CGM_hist)

        axes[0].draw_artist(axes[0].patch)
        axes[0].draw_artist(lines[0])
        axes[0].draw_artist(lines[1])

        adjust_ylim(axes[0], min(min(self.BG_hist), min(self.CGM_hist)), max(
            max(self.BG_hist), max(self.CGM_hist)))

        lines[2].set_xdata(self.time_hist[:-1])
        lines[2].set_ydata(self.CHO_hist)

        axes[1].draw_artist(axes[1].patch)
        axes[1].draw_artist(lines[2])

        adjust_ylim(axes[1], min(self.CHO_hist), max(self.CHO_hist))

        lines[3].set_xdata(self.time_hist[:-1])
        lines[3].set_ydata(self.insulin_hist)

        axes[2].draw_artist(axes[2].patch)
        axes[2].draw_artist(lines[3])
        adjust_ylim(axes[2], min(self.insulin_hist), max(self.insulin_hist))

        lines[4].set_xdata(self.time_hist)
        lines[4].set_ydata(self.LBGI_hist)

        lines[5].set_xdata(self.time_hist)
        lines[5].set_ydata(self.HBGI_hist)

        lines[6].set_xdata(self.time_hist)
        lines[6].set_ydata(self.risk_hist)

        axes[3].draw_artist(axes[3].patch)
        axes[3].draw_artist(lines[4])
        axes[3].draw_artist(lines[5])
        axes[3].draw_artist(lines[6])
        adjust_ylim(axes[3], min(self.risk_hist), max(self.risk_hist))

        # axes[0].clear()
        # axes[0].plot(self.time_hist, self.BG_hist, label='BG')
        # axes[0].plot(self.time_hist, self.CGM_hist,
        #              '*', markersize=1, label='CGM')
        # axes[0].set_ylabel('BG (mg/dL)')
        # axes[0].legend()

        # axes[1].clear()
        # axes[1].plot(self.time_hist[:-1], self.CHO_hist, label='CHO')
        # axes[1].set_ylabel('CHO (g/min)')
        # axes[1].legend()

        # axes[2].clear()
        # axes[2].plot(self.time_hist[:-1], self.insulin_hist, label='insulin')
        # axes[2].set_ylabel('Insulin (U/min)')
        # axes[2].legend()

        # axes[3].clear()
        # axes[3].plot(self.time_hist, self.risk_hist, label='Risk')
        # axes[3].plot(self.time_hist, self.LBGI_hist, label='Low BG Risk')
        # axes[3].plot(self.time_hist, self.HBGI_hist, label='High BG Risk')
        # axes[3].legend()

        # axes[3].xaxis.set_minor_locator(mdates.AutoDateLocator())
        # axes[3].xaxis.set_minor_formatter(mdates.DateFormatter('%H:%M\n'))
        # axes[3].xaxis.set_major_locator(mdates.DayLocator())
        # axes[3].xaxis.set_major_formatter(mdates.DateFormatter('\n%b %d'))
        # axes[3].set_ylabel('Risk Index')

    def show_history(self):
        df = pd.DataFrame()
        df['Time'] = pd.Series(self.time_hist)
        df['BG'] = pd.Series(self.BG_hist)
        df['CGM'] = pd.Series(self.CGM_hist)
        df['CHO'] = pd.Series(self.CHO_hist)
        df['insulin'] = pd.Series(self.insulin_hist)
        df['LBGI'] = pd.Series(self.LBGI_hist)
        df['HBGI'] = pd.Series(self.HBGI_hist)
        df['Risk'] = pd.Series(self.risk_hist)
        return df


def adjust_ylim(ax, ymin, ymax):
    ylim = ax.get_ylim()
    update = False

    if ymin < ylim[0]:
        y1 = ymin - 0.1 * abs(ymin)
        update = True
    else:
        y1 = ylim[0]

    if ymax > ylim[1]:
        y2 = ymax + 0.1 * abs(ymax)
        update = True
    else:
        y2 = ylim[1]

    if update:
        ax.set_ylim([y1, y2])
        for spine in ax.spines.values():
            ax.draw_artist(spine)
        ax.draw_artist(ax.yaxis)
