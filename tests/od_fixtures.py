"""pp_od_clk_voltage samples for each amdgpu generation (format per kernel amdgpu_pm.c / smu*_ppt.c)."""

POLARIS = """OD_SCLK:
0:        300MHz        750mV
1:        600MHz        769mV
2:        900MHz        881mV
3:       1145MHz        950mV
4:       1215MHz       1000mV
5:       1257MHz       1050mV
6:       1300MHz       1100mV
7:       1366MHz       1150mV
OD_MCLK:
0:        300MHz        750mV
1:       2000MHz        950mV
OD_RANGE:
SCLK:     300MHz       2000MHz
MCLK:     300MHz       2250MHz
VDDC:     750mV        1200mV
"""

NAVI10 = """OD_SCLK:
0: 800Mhz
1: 2100Mhz
OD_MCLK:
1: 875MHz
OD_VDDC_CURVE:
0: 800MHz 711mV
1: 1450MHz 801mV
2: 2100MHz 1191mV
OD_RANGE:
SCLK:     800Mhz       2150Mhz
MCLK:     625Mhz        950Mhz
VDDC_CURVE_SCLK[0]:     800Mhz       2150Mhz
VDDC_CURVE_VOLT[0]:     750mV        1200mV
VDDC_CURVE_SCLK[1]:     800Mhz       2150Mhz
VDDC_CURVE_VOLT[1]:     750mV        1200mV
VDDC_CURVE_SCLK[2]:     800Mhz       2150Mhz
VDDC_CURVE_VOLT[2]:     750mV        1200mV
"""

RDNA3 = """OD_SCLK:
0: 500Mhz
1: 2500Mhz
OD_MCLK:
0: 97Mhz
1: 1250MHz
OD_VDDGFX_OFFSET:
0mV
OD_RANGE:
SCLK:     500Mhz       3000Mhz
MCLK:      97Mhz       1500Mhz
VDDGFX_OFFSET:    -450mv          0mv
"""

RDNA4 = """OD_SCLK_OFFSET:
0Mhz
OD_MCLK:
0: 97Mhz
1: 1259MHz
OD_VDDGFX_OFFSET:
0mV
OD_RANGE:
SCLK_OFFSET:    -500Mhz      1000Mhz
MCLK:      97Mhz       1500Mhz
VDDGFX_OFFSET:    -200mv          0mv
"""

APU = """OD_SCLK:
0: 200Mhz
1: 2200Mhz
OD_RANGE:
SCLK:     200Mhz       2400Mhz
"""

FAN_CTRL = {
    "fan_curve": """OD_FAN_CURVE:
0: 0C 0%
1: 0C 0%
2: 0C 0%
3: 0C 0%
4: 0C 0%
OD_RANGE:
FAN_CURVE(hotspot temp): 25C 100C
FAN_CURVE(fan speed): 15% 100%
""",
    "fan_zero_rpm_enable": "FAN_ZERO_RPM_ENABLE:\n1\nOD_RANGE:\nZERO_RPM_ENABLE: 0 1\n",
    "fan_zero_rpm_stop_temperature": "FAN_ZERO_RPM_STOP_TEMPERATURE:\n50\nOD_RANGE:\nZERO_RPM_STOP_TEMPERATURE: 25 100\n",
    "fan_target_temperature": "FAN_TARGET_TEMPERATURE:\n95\nOD_RANGE:\nTARGET_TEMPERATURE: 25 110\n",
    "acoustic_limit_rpm_threshold": "OD_ACOUSTIC_LIMIT:\n2450\nOD_RANGE:\nACOUSTIC_LIMIT: 500 3100\n",
    "acoustic_target_rpm_threshold": "OD_ACOUSTIC_TARGET:\n2200\nOD_RANGE:\nACOUSTIC_TARGET: 500 3100\n",
    "fan_minimum_pwm": "FAN_MINIMUM_PWM:\n15\nOD_RANGE:\nMINIMUM_PWM: 15 100\n",
}
