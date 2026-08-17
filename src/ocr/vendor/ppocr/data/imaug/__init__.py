# copyright (c) 2020 PaddlePaddle Authors. All Rights Reserve.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

# NOTE(vendor-trim): 원본은 det/e2e/kie/table/vqa/formula 등 우리가 안 쓰는 알고리즘의
# 전처리 연산자까지 전부 이 파일에서 불러왔음. src/ocr/infer.py는 DecodeImage, RecResizeImg,
# KeepKeys만 leaf import로 직접 가져다 쓰므로, 이 파일 자체는 그것들을 안 불러와도 동작함
# (배경: src/ocr/README.md 참고).

from .operators import *
from .rec_img_aug import RecResizeImg


def transform(data, ops=None):
    """transform"""
    if ops is None:
        ops = []
    for op in ops:
        data = op(data)
        if data is None:
            return None
    return data


def create_operators(op_param_list, global_config=None):
    """
    create operators based on the config

    Args:
        params(list): a dict list, used to create some operators
    """
    assert isinstance(op_param_list, list), "operator config should be a list"
    ops = []
    for operator in op_param_list:
        assert isinstance(operator, dict) and len(operator) == 1, "yaml format error"
        op_name = list(operator)[0]
        param = {} if operator[op_name] is None else operator[op_name]
        if global_config is not None:
            param.update(global_config)
        op = eval(op_name)(**param)
        ops.append(op)
    return ops
