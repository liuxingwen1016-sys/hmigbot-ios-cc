@Entry
@Component
struct FontUnitFixture {
  build() {
    Column({ space: 12 }) {
      Text('Android dp → fixed vp').fontSize('18vp').id('font-vp')
      Text('Android sp → scaled fp').fontSize('18fp').id('font-fp')
      Text('Numeric ArkUI size is fp').fontSize(18).id('font-numeric')
    }
    .width('100%')
  }
}
