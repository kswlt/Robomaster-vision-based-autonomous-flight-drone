#!/usr/bin/env python3
"""Save SDK full calibration and compare bag CameraInfo with OpenVINS YAML.

No capture pipeline is started; the existing camera service retains ownership.
SDK output contains each profile's intrinsics and stream-to-stream extrinsics.
"""
import argparse
import json
from pathlib import Path
import subprocess
import yaml
import numpy as np
from analyze_sensor_timing import read_bag


def main():
    p=argparse.ArgumentParser(__doc__)
    p.add_argument('bag')
    p.add_argument('--config', default='/home/orangepi/vio_ws/src/open_vins/config/d430/kalibr_imucam_chain.yaml')
    p.add_argument('--output', default='results/vio_validation')
    a=p.parse_args()
    out=Path(a.output)
    out.mkdir(parents=True,exist_ok=True)
    sdk=subprocess.check_output(['/opt/ros/humble/bin/rs-enumerate-devices','-c'],timeout=30,text=True)
    (out/'realsense_factory_calibration.txt').write_text(sdk)
    config=yaml.safe_load('\n'.join(x for x in Path(a.config).read_text().splitlines() if not x.startswith('%YAML')))
    topics=['/camera/camera/infra1/camera_info','/camera/camera/infra2/camera_info']
    result={}
    for topic,m,_ in read_bag(a.bag,topics):
        if topic in result:
            continue
        cam=config['cam'+str(topics.index(topic))]
        rectified=[m.p[0],m.p[5],m.p[2],m.p[6]]
        result[topic]=dict(width=m.width,height=m.height,frame_id=m.header.frame_id,
                           distortion_model=m.distortion_model,K=list(m.k),D=list(m.d),R=list(m.r),P=list(m.p),
                           rectified_intrinsics=rectified,yaml_intrinsics=cam['intrinsics'],
                           yaml_minus_rectified=(np.array(cam['intrinsics'])-rectified).tolist(),
                           resolution_matches=cam['resolution']==[m.width,m.height],
                           yaml_distortion=cam['distortion_coeffs'])
        if len(result)==2:
            break
    (out/'camera_info_comparison.json').write_text(json.dumps(result,indent=2))
    if len(result)!=2:
        raise SystemExit('Missing CameraInfo: calibration not verified')
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
