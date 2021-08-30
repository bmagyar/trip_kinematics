from trip_kinematics.KinematicGroup import KinematicGroup, Transformation
from trip_kinematics.Robot import Robot, inverse_kinematics, forward_kinematics
from casadi import Opti, SX, Function, SX, nlpsol, vertcat
from typing import Dict, List
from trip_kinematics.HomogenTransformationMatrix import TransformationMatrix
import numpy as np
from math import radians, sin, cos


def c(rx, ry, rz):
    A_CSS_P_trans = TransformationMatrix(
        tx=0.265, ty=0, tz=0.014)

    A_CSS_P_rot = TransformationMatrix(
        conv='xyz', rx=rx, ry=ry, rz=rz)

    A_CSS_P = A_CSS_P_trans * A_CSS_P_rot

    T_P_SPH1_2 = np.array([-0.015, -0.029, 0.0965]) * -1
    T_P_SPH2_2 = np.array([-0.015, 0.029, 0.0965]) * -1
    x0, y0, z0 = T_P_SPH1_2
    x1, y1, z1 = T_P_SPH2_2

    A_P_SPH1_2 = TransformationMatrix(
        tx=x0, ty=y0, tz=z0, conv='xyz')
    A_P_SPH2_2 = TransformationMatrix(
        tx=x1, ty=y1, tz=z1, conv='xyz')

    A_c1 = A_CSS_P * A_P_SPH1_2
    A_c2 = A_CSS_P * A_P_SPH2_2

    c1 = A_c1.get_translation()
    c2 = A_c2.get_translation()
    return c1, c2


def p1(theta):
    A_CCS_lsm_tran = TransformationMatrix(
        tx=0.139807669447128, ty=0.0549998406976098, tz=-0.051)

    A_CCS_lsm_rot = TransformationMatrix(
        rz=radians(-338.5255), conv='xyz')  

    A_CCS_lsm = A_CCS_lsm_tran * A_CCS_lsm_rot

    A_MCS1_JOINT = TransformationMatrix(
        rz=theta, conv='xyz')

    A_CSS_MCS1 = A_CCS_lsm * A_MCS1_JOINT

    A_MCS1_SP11 = TransformationMatrix(
        tx=0.085, ty=0, tz=-0.0245)

    A_CCS_SP11 = A_CSS_MCS1 * A_MCS1_SP11

    p1 = A_CCS_SP11.get_translation()
    return p1


def p2(theta):
    A_CCS_rsm_tran = TransformationMatrix(
        tx=0.139807669447128, ty=-0.0549998406976098, tz=-0.051)

    A_CCS_rsm_rot = TransformationMatrix(
        rz=radians(-21.4745), conv='xyz')  

    A_CCS_rsm = A_CCS_rsm_tran*A_CCS_rsm_rot

    A_MCS2_JOINT = TransformationMatrix(
        rz=theta, conv='xyz')

    A_CSS_MCS2 = A_CCS_rsm * A_MCS2_JOINT

    A_MCS2_SP21 = TransformationMatrix(
        tx=0.085, ty=0, tz=-0.0245)

    A_CSS_SP21 = A_CSS_MCS2 * A_MCS2_SP21

    p2 = A_CSS_SP21.get_translation()
    return p2

theta_left  = SX.sym('theta_left')
theta_right = SX.sym('theta_right')
gimbal_x    = SX.sym('gimbal_x')
gimbal_y    = SX.sym('gimbal_y')
gimbal_z    = SX.sym('gimbal_z')

virtual_actuated_state = vertcat(theta_left,theta_right,gimbal_x,gimbal_y,gimbal_z)
opts                   = {'ipopt.print_level':0, 'print_time':0}
r                = 0.11
c1, c2           = c(rx=gimbal_x, ry=gimbal_y, rz=gimbal_z)
closing_equation = ((c1-p1(theta_right)).T @ (c1-p1(theta_right)) -r**2)**2+(
                    (c2-p2(theta_left)).T @ (c2-p2(theta_left)) -  r**2)**2


def swing_to_gimbal(state: Dict[str, float], tips: Dict[str, float] = None):
    x_0 = [state['swing_left'],state['swing_right'],0,0,0]
    if tips:
        x_0[2] = tips['rx']
        x_0[3] = tips['ry']
        x_0[4] = tips['rz']

    constraints = (theta_right - state['swing_right'])**2  + (theta_left - state['swing_left'])**2  

    nlp  = {'x':virtual_actuated_state ,'f':closing_equation,'g':constraints}
    mapping_solver = nlpsol('swing_to_gimbal','ipopt',nlp,opts)
    solution       = mapping_solver(x0 = x_0)
    sol_vector     = np.array(solution['x'])
    return {'gimbal_joint': {'rx': sol_vector[2][0], 'ry': sol_vector[3][0], 'rz': sol_vector[4][0]}}


def gimbal_to_swing(state: Dict[str,Dict[str, float]], tips: Dict[str, float] = None):
    x_0 = [0,0, state['gimbal_joint']['rx'], state['gimbal_joint']['ry'],state['gimbal_joint']['rz']]
    if tips:
        x_0[0] = tips['swing_left'] 
        x_0[1] = tips['swing_right']

    constraints = (gimbal_x - state['gimbal_joint']['rx'])**2  + (gimbal_y - state['gimbal_joint']['ry'])**2  + (gimbal_z - state['gimbal_joint']['rz'])**2
    
    nlp  = {'x':virtual_actuated_state ,'f':closing_equation,'g':constraints}
    reverse_mapping_solver = nlpsol('gimbal_to_swing','ipopt',nlp,opts)
    solution               = reverse_mapping_solver(x0 = [0,0,0,0,0])
    sol_vector             = np.array(solution['x'])
    return {'swing_left': sol_vector[0][0], 'swing_right': sol_vector[1][0]}


A_CSS_P_trans = Transformation(name='A_CSS_P_trans',
                               values={'tx': 0.265, 'tz': 0.014})

A_CSS_P_rot = Transformation(name='gimbal_joint',
                             values={'rx': 0, 'ry': 0, 'rz': 0}, state_variables=['rx', 'ry', 'rz'])

closed_chain = KinematicGroup(name='closed_chain', virtual_transformations=[A_CSS_P_trans,A_CSS_P_rot], 
                              actuated_state={'swing_left': 0, 'swing_right': 0}, 
                              actuated_to_virtual=swing_to_gimbal, virtual_to_actuated=gimbal_to_swing)

A_P_LL = Transformation(name='A_P_LL', values={'tx': 1.640, 'tz': -0.037, })

zero_angle_convention = Transformation(name='zero_angle_convention',
                                       values={'ry': radians(-3)})

extend_joint = Transformation(name='extend_joint',
                                   values={'ry': 0}, state_variables=['ry'])

A_LL_Joint_FCS = Transformation(name='A_LL_Joint_FCS', values={'tx': -1.5})

leg_linear_part = KinematicGroup(name='leg_linear_part',
                                 virtual_transformations=[A_P_LL, zero_angle_convention,extend_joint, A_LL_Joint_FCS], 
                                 parent=closed_chain)

triped_leg = Robot([closed_chain, leg_linear_part])

closed_chain.set_actuated_state({'swing_left': 0, 'swing_right': 0})
