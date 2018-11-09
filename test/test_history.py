import numpy as np

import torch

import pytest

from lagom.envs import make_gym_env
from lagom.envs import make_vec_env
from lagom.envs.vec_env import SerialVecEnv
from lagom.envs import EnvSpec

from lagom.history import Transition
from lagom.history import Trajectory
from lagom.history import Segment

from lagom.history import History

from lagom.history.metrics import terminal_state_from_trajectory
from lagom.history.metrics import terminal_state_from_segment
from lagom.history.metrics import final_state_from_trajectory
from lagom.history.metrics import final_state_from_segment
from lagom.history.metrics import bootstrapped_returns_from_trajectory
from lagom.history.metrics import bootstrapped_returns_from_segment
from lagom.history.metrics import td0_target
from lagom.history.metrics import td0_target_from_trajectory
from lagom.history.metrics import td0_target_from_segment
from lagom.history.metrics import td0_error
from lagom.history.metrics import td0_error_from_trajectory
from lagom.history.metrics import td0_error_from_segment
from lagom.history.metrics import gae
from lagom.history.metrics import gae_from_trajectory
from lagom.history.metrics import gae_from_segment


def test_transition():
    transition = Transition(s=1.2, a=2.0, r=-1.0, s_next=1.5, done=True)

    assert transition.s == 1.2
    assert transition.a == 2.0
    assert transition.r == -1.0
    assert transition.s_next == 1.5
    assert transition.done == True

    assert len(transition.info) == 0

    transition.add_info(name='V_s', value=0.3)
    transition.add_info(name='V_s_next', value=10.0)
    transition.add_info(name='extra', value=[1, 2, 3, 4])

    assert len(transition.info) == 3
    assert transition.get_info('V_s') == 0.3
    assert transition.get_info('V_s_next') == 10.0
    assert np.allclose(transition.info['extra'], [1, 2, 3, 4])
    
    
def test_trajectory():
    transition1 = Transition(s=1, a=0.1, r=0.5, s_next=2, done=False)
    transition1.add_info(name='V_s', value=10.0)

    transition2 = Transition(s=2, a=0.2, r=0.5, s_next=3, done=False)
    transition2.add_info(name='V_s', value=20.0)

    transition3 = Transition(s=3, a=0.3, r=1.0, s_next=4, done=True)
    transition3.add_info(name='V_s', value=30.0)
    transition3.add_info(name='V_s_next', value=40.0)  # Note that here non-zero value

    trajectory = Trajectory()

    assert len(trajectory.info) == 0
    assert trajectory.T == 0

    trajectory.add_info(name='extra', value=[1, 2, 3])
    assert len(trajectory.info) == 1
    assert np.allclose(trajectory.info['extra'], [1, 2, 3])

    trajectory.add_transition(transition=transition1)
    trajectory.add_transition(transition=transition2)
    trajectory.add_transition(transition=transition3)

    assert trajectory.T == 3

    # Test error to add one more transition, not allowed because last transition already done=True
    transition4 = Transition(s=0.1, a=0.1, r=1.0, s_next=0.2, done=False)
    with pytest.raises(AssertionError):
        trajectory.add_transition(transition=transition4)

    all_s = trajectory.all_s
    assert isinstance(all_s, tuple) and len(all_s) == 2
    assert np.allclose(all_s[0], [1, 2, 3])
    assert all_s[1] == 4
    assert np.allclose(trajectory.all_a, [0.1, 0.2, 0.3])
    assert np.allclose(trajectory.all_r, [0.5, 0.5, 1.0])
    assert np.allclose(trajectory.all_done, [False, False, True])
    assert np.allclose(trajectory.all_returns, [2.0, 1.5, 1.0])
    assert np.allclose(trajectory.all_discounted_returns(0.1), [0.56, 0.6, 1.0])
    assert np.allclose(trajectory.all_info(name='V_s'), [10, 20, 30])
    
    
def test_segment():
    # All test cases with following patterns of values
    # states: 10, 20, ...
    # rewards: 1, 2, ...
    # actions: -1, -2, ...
    # state_value: 100, 200, ...
    # discount: 0.1


    # Test case
    # Part of a single episode
    # [False, False, False, False]
    segment = Segment()

    transition1 = Transition(s=10, a=-1, r=1, s_next=20, done=False)
    transition1.add_info('V_s', torch.tensor(100.))
    segment.add_transition(transition1)

    transition2 = Transition(s=20, a=-2, r=2, s_next=30, done=False)
    transition2.add_info('V_s', torch.tensor(200.))
    segment.add_transition(transition2)

    transition3 = Transition(s=30, a=-3, r=3, s_next=40, done=False)
    transition3.add_info('V_s', torch.tensor(300.))
    segment.add_transition(transition3)

    transition4 = Transition(s=40, a=-4, r=4, s_next=50, done=False)
    transition4.add_info('V_s', torch.tensor(400.))
    transition4.add_info('V_s_next', torch.tensor(500.))
    assert len(transition4.info) == 2
    segment.add_transition(transition4)

    segment.add_info('extra', 'ok')
    assert len(segment.info) == 1

    # all_info
    all_info = segment.all_info('V_s')
    assert all([torch.is_tensor(info) for info in all_info])
    assert all_info[0].item() == 100.0
    assert all_info[-1].item() == 400.0

    assert segment.T == 4
    assert len(segment.trajectories) == 1
    assert segment.trajectories[0].T == 4

    all_s = segment.all_s
    assert isinstance(all_s, tuple) and len(all_s) == 2
    assert np.allclose(all_s[0], [10, 20, 30, 40])
    assert isinstance(all_s[1], tuple) and len(all_s[1]) == 1
    assert all_s[1][0] == 50
    assert np.allclose(segment.all_a, [-1, -2, -3, -4])
    assert np.allclose(segment.all_r, [1, 2, 3, 4])
    assert np.allclose(segment.all_done, [False, False, False, False])
    assert np.allclose(segment.all_returns, [10, 9, 7, 4])
    assert np.allclose(segment.all_discounted_returns(0.1), [1.234, 2.34, 3.4, 4])
    
    del segment
    del transition1
    del transition2
    del transition3
    del transition4
    del all_info


    # Test case
    # Part of a single episode with terminal state in final transition
    # [False, False, False, True]
    segment = Segment()

    transition1 = Transition(s=10, a=-1, r=1, s_next=20, done=False)
    transition1.add_info('V_s', torch.tensor(100.))
    segment.add_transition(transition1)

    transition2 = Transition(s=20, a=-2, r=2, s_next=30, done=False)
    transition2.add_info('V_s', torch.tensor(200.))
    segment.add_transition(transition2)

    transition3 = Transition(s=30, a=-3, r=3, s_next=40, done=False)
    transition3.add_info('V_s', torch.tensor(300.))
    segment.add_transition(transition3)

    transition4 = Transition(s=40, a=-4, r=4, s_next=50, done=True)
    transition4.add_info('V_s', torch.tensor(400.))
    transition4.add_info('V_s_next', torch.tensor(500.))
    assert len(transition4.info) == 2
    segment.add_transition(transition4)

    segment.add_info('extra', 'ok')
    assert len(segment.info) == 1

    # all_info
    all_info = segment.all_info('V_s')
    assert all([torch.is_tensor(info) for info in all_info])
    assert all_info[0].item() == 100.0
    assert all_info[-1].item() == 400.0

    assert segment.T == 4
    assert len(segment.trajectories) == 1
    assert segment.trajectories[0].T == 4
    assert len(segment.transitions) == 4

    all_s = segment.all_s
    assert isinstance(all_s, tuple) and len(all_s) == 2
    assert np.allclose(all_s[0], [10, 20, 30, 40])
    assert isinstance(all_s[1], tuple) and len(all_s[1]) == 1
    assert all_s[1][0] == 50
    assert np.allclose(segment.all_a, [-1, -2, -3, -4])
    assert np.allclose(segment.all_r, [1, 2, 3, 4])
    assert np.allclose(segment.all_done, [False, False, False, True])
    assert np.allclose(segment.all_returns, [10, 9, 7, 4])
    assert np.allclose(segment.all_discounted_returns(0.1), [1.234, 2.34, 3.4, 4])
    
    del segment
    del transition1
    del transition2
    del transition3
    del transition4
    del all_info


    # Test case
    # Two episodes (first episode terminates but second)
    # [False, True, False, False]
    segment = Segment()

    transition1 = Transition(s=10, a=-1, r=1, s_next=20, done=False)
    transition1.add_info('V_s', torch.tensor(100.))
    segment.add_transition(transition1)

    transition2 = Transition(s=20, a=-2, r=2, s_next=30, done=True)
    transition2.add_info('V_s', torch.tensor(200.))
    transition2.add_info('V_s_next', torch.tensor(250.))
    assert len(transition2.info) == 2
    segment.add_transition(transition2)

    transition3 = Transition(s=35, a=-3, r=3, s_next=40, done=False)
    transition3.add_info('V_s', torch.tensor(300.))
    segment.add_transition(transition3)

    transition4 = Transition(s=40, a=-4, r=4, s_next=50, done=False)
    transition4.add_info('V_s', torch.tensor(400.))
    transition4.add_info('V_s_next', torch.tensor(500.))
    assert len(transition4.info) == 2
    segment.add_transition(transition4)

    segment.add_info('extra', 'ok')
    assert len(segment.info) == 1

    # all_info
    all_info = segment.all_info('V_s')
    assert all([torch.is_tensor(info) for info in all_info])
    assert all_info[0].item() == 100.0
    assert all_info[-1].item() == 400.0

    assert segment.T == 4
    assert len(segment.trajectories) == 2
    assert segment.trajectories[0].T == 2
    assert segment.trajectories[1].T == 2
    assert len(segment.transitions) == 4

    all_s = segment.all_s
    assert isinstance(all_s, tuple) and len(all_s) == 2
    assert np.allclose(all_s[0], [10, 20, 35, 40])
    assert isinstance(all_s[1], tuple) and len(all_s[1]) == 2
    assert all_s[1] == (30, 50)
    assert np.allclose(segment.all_a, [-1, -2, -3, -4])
    assert np.allclose(segment.all_r, [1, 2, 3, 4])
    assert np.allclose(segment.all_done, [False, True, False, False])
    assert np.allclose(segment.all_returns, [3, 2, 7, 4])
    assert np.allclose(segment.all_discounted_returns(0.1), [1.2, 2, 3.4, 4])
    
    del segment
    del transition1
    del transition2
    del transition3
    del transition4
    del all_info


    # Test case
    # Three episodes (all terminates)
    # [True, True, False, True]
    segment = Segment()

    transition1 = Transition(s=10, a=-1, r=1, s_next=20, done=True)
    transition1.add_info('V_s', torch.tensor(100.))
    transition1.add_info('V_s_next', torch.tensor(150.))
    assert len(transition1.info) == 2
    segment.add_transition(transition1)

    transition2 = Transition(s=25, a=-2, r=2, s_next=30, done=True)
    transition2.add_info('V_s', torch.tensor(200.))
    transition2.add_info('V_s_next', torch.tensor(250.))
    assert len(transition2.info) == 2
    segment.add_transition(transition2)

    transition3 = Transition(s=35, a=-3, r=3, s_next=40, done=False)
    transition3.add_info('V_s', torch.tensor(300.))
    segment.add_transition(transition3)

    transition4 = Transition(s=40, a=-4, r=4, s_next=50, done=True)
    transition4.add_info('V_s', torch.tensor(400.))
    transition4.add_info('V_s_next', torch.tensor(500.))
    assert len(transition4.info) == 2
    segment.add_transition(transition4)

    segment.add_info('extra', 'ok')
    assert len(segment.info) == 1

    # all_info
    all_info = segment.all_info('V_s')
    assert all([torch.is_tensor(info) for info in all_info])
    assert all_info[0].item() == 100.0
    assert all_info[-1].item() == 400.0

    assert segment.T == 4
    assert len(segment.trajectories) == 3
    assert segment.trajectories[0].T == 1
    assert segment.trajectories[1].T == 1
    assert segment.trajectories[2].T == 2
    assert len(segment.transitions) == 4

    all_s = segment.all_s
    assert isinstance(all_s, tuple) and len(all_s) == 2
    assert np.allclose(all_s[0], [10, 25, 35, 40])
    assert isinstance(all_s[1], tuple) and len(all_s[1]) == 3
    assert all_s[1] == (20, 30, 50)
    assert np.allclose(segment.all_a, [-1, -2, -3, -4])
    assert np.allclose(segment.all_r, [1, 2, 3, 4])
    assert np.allclose(segment.all_done, [True, True, False, True])
    assert np.allclose(segment.all_returns, [1, 2, 7, 4])
    assert np.allclose(segment.all_discounted_returns(0.1), [1, 2, 3.4, 4])
    
    del segment
    del transition1
    del transition2
    del transition3
    del transition4
    del all_info
    
    
def test_history():
    env = make_vec_env(SerialVecEnv, make_gym_env, 'CartPole-v1', 3, 0)
    env_spec = EnvSpec(env)
    history = History(env_spec, T=5)

    assert history.env_spec is env_spec
    assert history.N == 3
    assert history.T == 5
    assert history.observations.shape == (3, 5+1, 4)
    assert history.rewards.shape == (3, 5)
    assert history.dones.shape == (3, 5)
    assert len(history.infos) == 5
    assert len(history.extra_info) == 0

    history.add_extra_info('roger', 20)
    assert history.extra_info['roger'] == 20

    history.add('one', 1)
    assert history.one == 1
    assert history.get('one') == 1
    with pytest.raises(AssertionError):
        history.add('one', 2)

    history.add_t('oh', 3, -5)
    assert hasattr(history, 'oh')
    assert history.oh == [None, None, None, -5, None]
    assert history.oh[3] == -5
    assert history.get_t('oh', 3) == -5

    init_obs = env.reset()
    history.observations[:, 0, ...] = init_obs
    obs, reward, done, info = env.step([0]*3)
    history.observations[:, 1, ...] = obs
    history.rewards[:, 0] = reward
    history.dones[:, 0] = done
    history.infos[0] = info

    assert np.allclose(init_obs, history.observations[:, 0, ...])
    assert np.allclose(obs, history.observations[:, 1, ...])
    assert np.allclose(0.0, history.observations[:, 2:, ...])
    assert np.allclose(reward, history.rewards[:, 0])
    assert np.allclose(0.0, history.rewards[:, 1:])
    assert np.allclose(done, history.dones[:, 0])
    assert np.allclose(True, history.dones[:, 1:])
    assert history.infos[0] == [{}, {}, {}]
    assert history.infos[1:] == [None, None, None, None]

    assert np.allclose(history.masks[:, 0], int(not False))
    assert np.allclose(history.masks[:, 1:], int(not True))


def test_terminal_state_from_trajectory():
    t = Trajectory()
    t.add_transition(Transition(1.0, 10, 0.1, 2.0, False))
    t.add_transition(Transition(2.0, 20, 0.2, 3.0, False))
    t.add_transition(Transition(3.0, 30, 0.3, 4.0, True))
    
    assert terminal_state_from_trajectory(t) == 4.0
    
    t = Trajectory()
    t.add_transition(Transition(1.0, 10, 0.1, 2.0, False))
    t.add_transition(Transition(2.0, 20, 0.2, 3.0, False))
    t.add_transition(Transition(3.0, 30, 0.3, 4.0, False))
    
    assert terminal_state_from_trajectory(t) is None
    
    with pytest.raises(AssertionError):
        terminal_state_from_segment(t)

def test_terminal_state_from_segment():
    s = Segment()
    s.add_transition(Transition(1.0, 10, 0.1, 2.0, False))
    s.add_transition(Transition(2.0, 20, 0.2, 3.0, False))
    s.add_transition(Transition(3.0, 30, 0.3, 4.0, True))
    s.add_transition(Transition(5.0, 50, 0.5, 6.0, False))
    s.add_transition(Transition(6.0, 60, 0.6, 7.0, True))
    assert terminal_state_from_segment(s) == [4.0, 7.0]

    s = Segment()
    s.add_transition(Transition(1.0, 10, 0.1, 2.0, False))
    s.add_transition(Transition(2.0, 20, 0.2, 3.0, False))
    s.add_transition(Transition(3.0, 30, 0.3, 4.0, True))
    s.add_transition(Transition(5.0, 50, 0.5, 6.0, False))
    s.add_transition(Transition(6.0, 60, 0.6, 7.0, False))
    assert terminal_state_from_segment(s) == [4.0]
    
    with pytest.raises(AssertionError):
        terminal_state_from_trajectory(s)
        
        
def test_final_state_from_trajectory():
    t = Trajectory()
    t.add_transition(Transition(1.0, 10, 0.1, 2.0, False))
    t.add_transition(Transition(2.0, 20, 0.2, 3.0, False))
    t.add_transition(Transition(3.0, 30, 0.3, 4.0, True))
    
    assert final_state_from_trajectory(t) == 4.0
    
    t = Trajectory()
    t.add_transition(Transition(1.0, 10, 0.1, 2.0, False))
    t.add_transition(Transition(2.0, 20, 0.2, 3.0, False))
    t.add_transition(Transition(3.0, 30, 0.3, 4.0, False))
    
    assert final_state_from_trajectory(t) == 4.0
    
    with pytest.raises(AssertionError):
        final_state_from_segment(t)
        
        
def test_final_state_from_segment():
    s = Segment()
    s.add_transition(Transition(1.0, 10, 0.1, 2.0, False))
    s.add_transition(Transition(2.0, 20, 0.2, 3.0, False))
    s.add_transition(Transition(3.0, 30, 0.3, 4.0, True))
    s.add_transition(Transition(5.0, 50, 0.5, 6.0, False))
    s.add_transition(Transition(6.0, 60, 0.6, 7.0, True))
    assert final_state_from_segment(s) == [4.0, 7.0]

    s = Segment()
    s.add_transition(Transition(1.0, 10, 0.1, 2.0, False))
    s.add_transition(Transition(2.0, 20, 0.2, 3.0, False))
    s.add_transition(Transition(3.0, 30, 0.3, 4.0, True))
    s.add_transition(Transition(5.0, 50, 0.5, 6.0, False))
    s.add_transition(Transition(6.0, 60, 0.6, 7.0, False))
    assert final_state_from_segment(s) == [4.0, 7.0]
    
    with pytest.raises(AssertionError):
        final_state_from_trajectory(s)

        
def test_bootstrapped_returns_from_trajectory():
    t = Trajectory()
    t.add_transition(Transition(1.0, 10, 0.1, 2.0, False))
    t.add_transition(Transition(2.0, 20, 0.2, 3.0, False))
    t.add_transition(Transition(3.0, 30, 0.3, 4.0, True))
    V_last = 100
    
    out =  bootstrapped_returns_from_trajectory(t, V_last, 1.0)
    assert np.allclose(out, [0.6, 0.5, 0.3])
    out =  bootstrapped_returns_from_trajectory(t, V_last, 0.1)
    assert np.allclose(out, [0.123, 0.23, 0.3])
    
    t = Trajectory()
    t.add_transition(Transition(1.0, 10, 0.1, 2.0, False))
    t.add_transition(Transition(2.0, 20, 0.2, 3.0, False))
    t.add_transition(Transition(3.0, 30, 0.3, 4.0, False))
    V_last = 100
    
    out = bootstrapped_returns_from_trajectory(t, V_last, 1.0)
    assert np.allclose(out, [100.6, 100.5, 100.3])
    out = bootstrapped_returns_from_trajectory(t, V_last, 0.1)
    assert np.allclose(out, [0.223, 1.23, 10.3])
    
    with pytest.raises(AssertionError):
        bootstrapped_returns_from_segment(t, V_last, 1.0)
        
        
def test_bootstrapped_returns_from_segment():
    s = Segment()
    s.add_transition(Transition(1.0, 10, 0.1, 2.0, False))
    s.add_transition(Transition(2.0, 20, 0.2, 3.0, False))
    s.add_transition(Transition(3.0, 30, 0.3, 4.0, True))
    s.add_transition(Transition(5.0, 50, 0.5, 6.0, False))
    s.add_transition(Transition(6.0, 60, 0.6, 7.0, True))
    all_V_last = [50, 100]
    
    out = bootstrapped_returns_from_segment(s, all_V_last, 1.0)
    assert np.allclose(out, [0.6, 0.5, 0.3, 1.1, 0.6])
    out = bootstrapped_returns_from_segment(s, all_V_last, 0.1)
    assert np.allclose(out, [0.123, 0.23, 0.3, 0.56, 0.6])

    s = Segment()
    s.add_transition(Transition(1.0, 10, 0.1, 2.0, False))
    s.add_transition(Transition(2.0, 20, 0.2, 3.0, False))
    s.add_transition(Transition(3.0, 30, 0.3, 4.0, True))
    s.add_transition(Transition(5.0, 50, 0.5, 6.0, False))
    s.add_transition(Transition(6.0, 60, 0.6, 7.0, False))
    all_V_last = [50, 100]
    
    out = bootstrapped_returns_from_segment(s, all_V_last, 1.0)
    assert np.allclose(out, [0.6, 0.5, 0.3, 101.1, 100.6])
    out = bootstrapped_returns_from_segment(s, all_V_last, 0.1)
    assert np.allclose(out, [0.123, 0.23, 0.3, 1.56, 10.6])
    
    with pytest.raises(AssertionError):
        bootstrapped_returns_from_trajectory(s, all_V_last, 1.0)


def test_td0_target():
    with pytest.raises(AssertionError):
        td0_target((0.1, 0.2), (1, 2, 3), 0.1)
    with pytest.raises(AssertionError):
        td0_target([0.1, 0.2], [1, 2], 0.1)
    with pytest.raises(AssertionError):
        td0_target([0.1, 0.2], [1, 2, 3], -1)
    with pytest.raises(AssertionError):
        td0_target([0.1, 0.2], [1, 2, 3], 1.1)
    
    out = td0_target([0.1, 0.2, 0.3, 0.4], [1, 2, 3, 4, 5], 0.1)
    assert np.allclose(out, [0.3, 0.5, 0.7, 0.9])
    
    out = td0_target([0.1, 0.2, 0.3, 0.4], [1, 2, 3, 4, 0], 0.1)
    assert np.allclose(out, [0.3, 0.5, 0.7, 0.4])        

    
@pytest.mark.parametrize('mode', ['tensor', 'array', 'raw'])
def test_td0_target_from_trajectory(mode):
    def make_x(x):
        if mode == 'tensor':
            return torch.tensor(x)
        elif mode == 'array':
            return np.array(x)
        elif mode == 'raw':
            return x

    traj = Trajectory()
    t1 = Transition(1.0, 10, 0.1, 2.0, False)
    t1.add_info('V_s', make_x(1.0))
    traj.add_transition(t1)
    t2 = Transition(2.0, 20, 0.2, 3.0, False)
    t2.add_info('V_s', make_x(2.0))
    traj.add_transition(t2)
    t3 = Transition(3.0, 30, 0.3, 4.0, False)
    t3.add_info('V_s', make_x(3.0))
    traj.add_transition(t3)
    t4 = Transition(4.0, 40, 0.4, 5.0, False)
    t4.add_info('V_s', make_x(4.0))
    t4.add_info('V_s_next', make_x(5.0))
    traj.add_transition(t4)

    with pytest.raises(AssertionError):
        td0_target_from_trajectory([1, 2], traj.all_info('V_s'), traj.transitions[-1].info['V_s_next'], 0.1)
    with pytest.raises(AssertionError):
        td0_target_from_trajectory(traj, traj.all_info('V_s')+[0], traj.transitions[-1].info['V_s_next'], 0.1)

    assert not traj.complete
    out = td0_target_from_trajectory(traj, traj.all_info('V_s'), traj.transitions[-1].info['V_s_next'], 0.1)
    assert np.allclose(out, [0.3, 0.5, 0.7, 0.9])

    traj.transitions[-1].done = True
    assert traj.complete
    out = td0_target_from_trajectory(traj, traj.all_info('V_s'), traj.transitions[-1].info['V_s_next'], 0.1)
    assert np.allclose(out, [0.3, 0.5, 0.7, 0.4])

    
@pytest.mark.parametrize('mode', ['tensor', 'array', 'raw'])
def test_td0_target_from_segment(mode):
    def make_x(x):
        if mode == 'tensor':
            return torch.tensor(x)
        elif mode == 'array':
            return np.array(x)
        elif mode == 'raw':
            return x

    seg = Segment()
    t1 = Transition(1.0, 10, 0.1, 2.0, False)
    t1.add_info('V_s', make_x(1.0))
    seg.add_transition(t1)
    t2 = Transition(2.0, 20, 0.2, 3.0, False)
    t2.add_info('V_s', make_x(2.0))
    seg.add_transition(t2)
    t3 = Transition(3.0, 30, 0.3, 4.0, True)
    t3.add_info('V_s', make_x(3.0))
    t3.add_info('V_s_next', make_x(4.0))
    seg.add_transition(t3)
    t4 = Transition(5.0, 50, 0.5, 6.0, False)
    t4.add_info('V_s', make_x(1.0))
    seg.add_transition(t4)
    t5 = Transition(6.0, 60, 0.6, 7.0, True)
    t5.add_info('V_s', make_x(2.0))
    t5.add_info('V_s_next', make_x(3.0))
    seg.add_transition(t5)
    
    all_Vs = [traj.all_info('V_s') for traj in seg.trajectories]
    all_V_last = [traj.transitions[-1].info['V_s_next'] for traj in seg.trajectories]
    
    with pytest.raises(AssertionError):
        td0_target_from_segment([1, 2], all_Vs, all_V_last, 0.1)
    with pytest.raises(AssertionError):
        td0_target_from_segment(seg, all_Vs+[0], all_V_last, 0.1)
    with pytest.raises(AssertionError):
        td0_target_from_segment(seg, all_Vs, all_V_last+[0], 0.1)

    out = td0_target_from_segment(seg, all_Vs, all_V_last, 0.1)
    assert np.allclose(out, [0.3, 0.5, 0.3, 0.7, 0.6])
    
    seg.transitions[-1].done = False
    out = td0_target_from_segment(seg, all_Vs, all_V_last, 0.1)
    assert np.allclose(out, [0.3, 0.5, 0.3, 0.7, 0.9])
    
    
def test_td0_error():
    with pytest.raises(AssertionError):
        td0_error((0.1, 0.2), (1, 2, 3), 0.1)
    with pytest.raises(AssertionError):
        td0_error([0.1, 0.2], [1, 2], 0.1)
    with pytest.raises(AssertionError):
        td0_error([0.1, 0.2], [1, 2, 3], -1)
    with pytest.raises(AssertionError):
        td0_error([0.1, 0.2], [1, 2, 3], 1.1)
        
    out = td0_error([0.1, 0.2, 0.3, 0.4], [1, 2, 3, 4, 5], 0.1)
    assert np.allclose(out, [-0.7, -1.5, -2.3, -3.1])
    
    out = td0_error([0.1, 0.2, 0.3, 0.4], [1, 2, 3, 4, 0], 0.1)
    assert np.allclose(out, [-0.7, -1.5, -2.3, -3.6])

    
@pytest.mark.parametrize('mode', ['tensor', 'array', 'raw'])
def test_td0_error_from_trajectory(mode):
    def make_x(x):
        if mode == 'tensor':
            return torch.tensor(x)
        elif mode == 'array':
            return np.array(x)
        elif mode == 'raw':
            return x

    traj = Trajectory()
    t1 = Transition(1.0, 10, 0.1, 2.0, False)
    t1.add_info('V_s', make_x(1.0))
    traj.add_transition(t1)
    t2 = Transition(2.0, 20, 0.2, 3.0, False)
    t2.add_info('V_s', make_x(2.0))
    traj.add_transition(t2)
    t3 = Transition(3.0, 30, 0.3, 4.0, False)
    t3.add_info('V_s', make_x(3.0))
    traj.add_transition(t3)
    t4 = Transition(4.0, 40, 0.4, 5.0, False)
    t4.add_info('V_s', make_x(4.0))
    t4.add_info('V_s_next', make_x(5.0))
    traj.add_transition(t4)

    with pytest.raises(AssertionError):
        td0_error_from_trajectory([1, 2], traj.all_info('V_s'), traj.transitions[-1].info['V_s_next'], 0.1)
    with pytest.raises(AssertionError):
        td0_error_from_trajectory(traj, traj.all_info('V_s')+[0], traj.transitions[-1].info['V_s_next'], 0.1)

    assert not traj.complete
    out = td0_error_from_trajectory(traj, traj.all_info('V_s'), traj.transitions[-1].info['V_s_next'], 0.1)
    assert np.allclose(out, [-0.7, -1.5, -2.3, -3.1])

    traj.transitions[-1].done = True
    assert traj.complete
    out = td0_error_from_trajectory(traj, traj.all_info('V_s'), traj.transitions[-1].info['V_s_next'], 0.1)
    assert np.allclose(out, [-0.7, -1.5, -2.3, -3.6])

    
@pytest.mark.parametrize('mode', ['tensor', 'array', 'raw'])
def test_td0_error_from_segment(mode):
    def make_x(x):
        if mode == 'tensor':
            return torch.tensor(x)
        elif mode == 'array':
            return np.array(x)
        elif mode == 'raw':
            return x

    seg = Segment()
    t1 = Transition(1.0, 10, 0.1, 2.0, False)
    t1.add_info('V_s', make_x(1.0))
    seg.add_transition(t1)
    t2 = Transition(2.0, 20, 0.2, 3.0, False)
    t2.add_info('V_s', make_x(2.0))
    seg.add_transition(t2)
    t3 = Transition(3.0, 30, 0.3, 4.0, True)
    t3.add_info('V_s', make_x(3.0))
    t3.add_info('V_s_next', make_x(4.0))
    seg.add_transition(t3)
    t4 = Transition(5.0, 50, 0.5, 6.0, False)
    t4.add_info('V_s', make_x(1.0))
    seg.add_transition(t4)
    t5 = Transition(6.0, 60, 0.6, 7.0, True)
    t5.add_info('V_s', make_x(2.0))
    t5.add_info('V_s_next', make_x(3.0))
    seg.add_transition(t5)
    
    all_Vs = [traj.all_info('V_s') for traj in seg.trajectories]
    all_V_last = [traj.transitions[-1].info['V_s_next'] for traj in seg.trajectories]
    
    with pytest.raises(AssertionError):
        td0_error_from_segment([1, 2], all_Vs, all_V_last, 0.1)
    with pytest.raises(AssertionError):
        td0_error_from_segment(seg, all_Vs+[0], all_V_last, 0.1)
    with pytest.raises(AssertionError):
        td0_error_from_segment(seg, all_Vs, all_V_last+[0], 0.1)

    out = td0_error_from_segment(seg, all_Vs, all_V_last, 0.1)
    assert np.allclose(out, [-0.7, -1.5, -2.7, -0.3, -1.4])
    
    seg.transitions[-1].done = False
    out = td0_error_from_segment(seg, all_Vs, all_V_last, 0.1)
    assert np.allclose(out, [-0.7, -1.5, -2.7, -0.3, -1.1])
    
    
def test_gae():
    with pytest.raises(AssertionError):
        gae((1, 2, 3, 4, 5), 0.5, 0.2)
    with pytest.raises(AssertionError):
        gae([1, 2, 3, 4, 5], -1, -1)
    with pytest.raises(AssertionError):
        gae([1, 2, 3, 4, 5], 1.1, 1.1)
    
    gamma = 0.5
    lam = 0.2
    out = gae([1, 2, 3, 4, 5], gamma, lam)
    assert np.allclose(out, [1.2345, 2.345, 3.45, 4.5, 5])
    
    
@pytest.mark.parametrize('mode', ['tensor', 'array', 'raw'])
def test_gae_from_trajectory(mode):
    def make_x(x):
        if mode == 'tensor':
            return torch.tensor(x)
        elif mode == 'array':
            return np.array(x)
        elif mode == 'raw':
            return x

    traj = Trajectory()
    t1 = Transition(1.0, 10, 0.1, 2.0, False)
    t1.add_info('V_s', make_x(1.0))
    traj.add_transition(t1)
    t2 = Transition(2.0, 20, 0.2, 3.0, False)
    t2.add_info('V_s', make_x(2.0))
    traj.add_transition(t2)
    t3 = Transition(3.0, 30, 0.3, 4.0, False)
    t3.add_info('V_s', make_x(3.0))
    traj.add_transition(t3)
    t4 = Transition(4.0, 40, 0.4, 5.0, False)
    t4.add_info('V_s', make_x(4.0))
    t4.add_info('V_s_next', make_x(5.0))
    traj.add_transition(t4)
    assert not traj.complete
    
    gamma = 0.2
    lam = 0.5
    
    Vs = traj.all_info('V_s')
    V_last = traj.transitions[-1].info['V_s_next']
    out = gae_from_trajectory(traj, Vs, V_last, gamma, lam)
    assert np.allclose(out, [-0.6416, -1.416, -2.16, -2.6])
    
    traj.transitions[-1].done = True
    assert traj.complete
    Vs = traj.all_info('V_s')
    V_last = traj.transitions[-1].info['V_s_next']
    out = gae_from_trajectory(traj, Vs, V_last, gamma, lam)
    assert np.allclose(out, [-0.6426, -1.426, -2.26, -3.6])

    
@pytest.mark.parametrize('mode', ['tensor', 'array', 'raw'])
def test_gae_from_segment(mode):
    def make_x(x):
        if mode == 'tensor':
            return torch.tensor(x)
        elif mode == 'array':
            return np.array(x)
        elif mode == 'raw':
            return x

    seg = Segment()
    t1 = Transition(1.0, 10, 0.1, 2.0, False)
    t1.add_info('V_s', make_x(1.0))
    seg.add_transition(t1)
    t2 = Transition(2.0, 20, 0.2, 3.0, False)
    t2.add_info('V_s', make_x(2.0))
    seg.add_transition(t2)
    t3 = Transition(3.0, 30, 0.3, 4.0, True)
    t3.add_info('V_s', make_x(3.0))
    t3.add_info('V_s_next', make_x(4.0))
    seg.add_transition(t3)
    t4 = Transition(5.0, 50, 0.5, 6.0, False)
    t4.add_info('V_s', make_x(1.0))
    seg.add_transition(t4)
    t5 = Transition(6.0, 60, 0.6, 7.0, True)
    t5.add_info('V_s', make_x(2.0))
    t5.add_info('V_s_next', make_x(3.0))
    seg.add_transition(t5)
    
    gamma = 0.2
    lam = 0.5
    
    all_Vs = [traj.all_info('V_s') for traj in seg.trajectories]
    all_V_last = [traj.transitions[-1].info['V_s_next'] for traj in seg.trajectories]
    out = gae_from_segment(seg, all_Vs, all_V_last, gamma, lam)
    assert np.allclose(out, [-0.647, -1.47, -2.7, -0.24, -1.4])
    
    seg.transitions[-1].done = False
    all_Vs = [traj.all_info('V_s') for traj in seg.trajectories]
    all_V_last = [traj.transitions[-1].info['V_s_next'] for traj in seg.trajectories]
    out = gae_from_segment(seg, all_Vs, all_V_last, gamma, lam)
    assert np.allclose(out, [-0.647, -1.47, -2.7, -0.18, -0.8])