@Component
export struct DetailViewController {
  build() {
    Column({ space: 12 }) {
      Text($r('app.string.detail_title'))
      Button('Done')
    }
  }
}
