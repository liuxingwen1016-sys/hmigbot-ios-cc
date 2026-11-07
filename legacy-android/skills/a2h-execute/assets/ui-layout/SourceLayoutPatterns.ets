/** Runnable layout patterns, not weather-app implementation or screenshot fixtures. */
@ComponentV2
export struct SourceRightAnchor {
  @Param label: string = 'right';
  build() {
    Row() {
      Text(this.label)
        .width(75)
        .height(50)
        .textAlign(TextAlign.Center)
        .backgroundColor('#D2F4E5')
    }
    .width('100%')
    .height(110)
    .justifyContent(FlexAlign.End)
    .padding({ right: 16 })
  }
}

@ComponentV2
export struct SourceBottomAnchor {
  @Param label: string = 'bottom';
  build() {
    Column() {
      Text(this.label)
        .width('100%')
        .height(40)
        .backgroundColor('#D2F4E5')
    }
    .width('100%')
    .height(110)
    .justifyContent(FlexAlign.End)
    .padding({ bottom: 8 })
  }
}

@ComponentV2
export struct SourceShortScroll {
  @Param label: string = 'top';
  build() {
    Scroll() {
      Column() {
        Text(this.label).height(30).width('100%').backgroundColor('#D2F4E5')
      }.width('100%')
    }
    .width('100%')
    .height(110)
    .align(Alignment.Top)
  }
}

@ComponentV2
export struct SourceCalendarRows {
  @Param cells: string[] = [];
  @Param rows: number = 6;
  build() {
    Grid() {
      ForEach(this.cells, (cell: string) => {
        GridItem() { Text(cell).fontSize(12) }.height(28)
      }, (cell: string) => cell)
    }
    .columnsTemplate('1fr 1fr 1fr 1fr 1fr 1fr 1fr')
    .rowsTemplate(this.rows === 6 ? '1fr 1fr 1fr 1fr 1fr 1fr' : '1fr 1fr 1fr 1fr 1fr')
    .height(this.rows * 28)
    .width('100%')
  }
}
