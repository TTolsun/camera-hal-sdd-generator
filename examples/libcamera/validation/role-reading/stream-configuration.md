# 앱이 요청한 USB 뷰파인더 크기를 어디까지 추적할 수 있나

기준 소스는 libcamera `adfa719f8ed67d18fd8a0739fc088a1f8b9e7252`다. [기준 공개판](https://github.com/TTolsun/libcamera-sdd/tree/ec95369614b2a80631e53c1e5447132ce481fa06/docs)의 빌드 ID는 `bd487ad37969d729667eceb2c24c8b86c285145d0c764c0a1f4288b8c9ec2c29`다.

공식 앱 가이드에서 뷰파인더 한 개를 만들고 크기를 640×480으로 바꾼 뒤 검증 결과를 읽는 사례를 선택했다. 가이드의 320×240은 조정이 가능한 한 예다. 장치 구현은 고정된 소스의 UVC 핸들러를 사용한다. 공식 핸들러 가이드의 Vivid는 별도의 교육용 구현이다. [앱의 구성 검증](https://docs.libcamera.org/master/guides/application-developer.html#change-and-validate-the-configuration) · [핸들러의 구성 적용](https://docs.libcamera.org/master/guides/pipeline-handler.html#configuring-a-device)

## 독자에게 준 과제

ForDeveloper에서 시작한다. USB 카메라에 640×480을 요청했을 때 앱이 다시 읽을 값과 장치가 적용하려는 값을 찾아 설명한다. 요청값과 다른 경우에도 계속할 수 있는 시점과 오류로 돌아오는 시점을 구별한다. 실제 보드에서 확인할 결과를 적는다. 독자에게는 고정 사이트와 그 안의 코드 발췌만 제공한다.

수정 전 독자는 `for-developer.html#configure`에서 공통 검증과 핸들러의 반환값을 찾고 기능·지원 범위에서 앱이 조정된 값을 확인하는 절을 찾았다. 진단 자료가 UVC 검증 함수를 후보로 언급했지만, 확인한 한국어 페이지 34개에서는 UVC가 검증한 크기를 장치에 넘기는 지점과 드라이버가 다른 값을 반환했을 때의 결과를 연결할 수 없었다. 공개된 가상 카메라의 400×300 관측값은 이 USB 카메라의 결과로 해석하지 않았다.
