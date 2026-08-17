# Copyright (c) 2020 PaddlePaddle Authors. All Rights Reserved.
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
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

# NOTE(vendor-trim): 원본은 det/e2e/kie/table/vqa 등 우리가 안 쓰는 알고리즘의 후처리
# 클래스까지 전부 이 파일에서 불러왔음. src/ocr/infer.py는 CTCLabelDecode만 leaf import로
# 직접 가져다 쓰므로, 이 파일 자체는 그것도 안 불러와도 동작함 (배경: src/ocr/README.md 참고).
