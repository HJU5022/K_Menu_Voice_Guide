# Copyright (c) 2019 PaddlePaddle Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# NOTE(vendor-trim): 이 안의 파일들이 서로를 `from ppocr.xxx import yyy` 절대경로 방식으로
# 참조하기 때문에, "ppocr"가 최상위 패키지로 보이도록 부모 폴더(src/ocr/vendor/)를
# sys.path에 추가해줘야 함. 원래 ppocr/data/__init__.py에 있던 로직인데,
# data를 안 거쳐도 항상 적용되도록 여기(패키지 최상단)로 옮김.
import os
import sys

_VENDOR_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _VENDOR_DIR not in sys.path:
    sys.path.append(_VENDOR_DIR)
