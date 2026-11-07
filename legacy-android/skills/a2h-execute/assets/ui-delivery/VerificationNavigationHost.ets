import { ValidatedVerificationContext, needsVerificationNavigation } from './VerificationContext';
import { VerificationSession, verificationSession } from './VerificationSession';

// No @Entry, no replacement pageMap, no preview copy of the page or VM.
// Owner passes a builder that delegates to its ORIGINAL pageMap.
@ComponentV2
export struct VerificationNavigationHost {
  @Local session: VerificationSession = verificationSession;
  @Provider('navPathStack') navPathStack: NavPathStack = new NavPathStack();
  private lastRequestKey: string = '';

  @Require @BuilderParam pageMap: (name: string, param: Object) => void;

  aboutToAppear(): void {
    this.synchronize();
  }

  @Monitor('session.revision')
  onNewRequest(): void {
    this.synchronize();
  }

  private synchronize(): void {
    const context: ValidatedVerificationContext | undefined = this.session.context;
    if (context === undefined) {
      this.navPathStack.clear(false);
      this.lastRequestKey = '';
      return;
    }
    if (!needsVerificationNavigation(this.lastRequestKey, context, this.navPathStack.size())) {
      return;
    }
    this.navPathStack.clear(false);
    this.navPathStack.pushPath({ name: context.routeName, param: context }, false);
    this.lastRequestKey = context.requestKey;
  }

  build() {
    Navigation(this.navPathStack) {
      Column({ space: 16 }) {
        Text('UI verification host').id('verification_host_title')
          .fontSize(20).fontColor('#333333')
        Button('Exit verification').id('verification_host_exit')
          .onClick(() => this.session.clear())
      }.width('100%').height('100%').justifyContent(FlexAlign.Center)
        .backgroundColor('#FFFFFF')
    }
    .navDestination(this.pageMap)
    .mode(NavigationMode.Stack)
    .hideTitleBar(true)
  }
}
