@Entry
@Component
struct HomeView {
  @State count: number = 0;

  build() {
    Navigation() {
      Column({ space: 16 }) {
        Image($r('app.media.logo')).width(48).height(48)
        Text($r('app.string.home_title'))
        Button('Open detail').onClick(() => { this.count += 1 })
      }.padding(24)
    }
  }
}
