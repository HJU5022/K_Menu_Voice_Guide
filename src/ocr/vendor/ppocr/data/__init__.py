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

# NOTE(vendor-trim): 원본은 학습용 DataLoader(build_dataloader)와 여러 Dataset 클래스를
# 이 파일에서 불러왔음. src/ocr/infer.py는 추론만 하고 학습 데이터로더를 안 쓰므로,
# 그 부분은 다 지웠음 (배경: src/ocr/README.md 참고). data.imaug 하위 모듈은 그대로 유지.
