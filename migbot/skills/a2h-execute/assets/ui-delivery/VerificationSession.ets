import { Want } from '@kit.AbilityKit';
import { ValidatedVerificationContext } from './VerificationContext';
import { resolveVerificationWant } from './VerificationResolver';

export interface VerificationDisposable {
  dispose(): void;
}

@ObservedV2
export class VerificationSession {
  @Trace context: ValidatedVerificationContext | undefined = undefined;
  @Trace revision: number = 0;
  private disposables: VerificationDisposable[] = [];

  // The original VM owner registers its subscription/provider cleanup once.
  retain(disposable: VerificationDisposable): void {
    if (this.context === undefined) {
      disposable.dispose();
      return;
    }
    this.disposables.push(disposable);
  }

  private disposeCurrent(): void {
    const previous: VerificationDisposable[] = this.disposables;
    this.disposables = [];
    for (const disposable of previous) {
      disposable.dispose();
    }
  }

  // Call for BOTH onCreate and onNewWant, including normal/invalid Wants.
  // Clearing before normal handling prevents a previous fixture leaking into real UI.
  acceptWant(want: Want): boolean {
    const next: ValidatedVerificationContext | undefined = resolveVerificationWant(want);
    if (next === undefined || this.context?.requestKey !== next.requestKey) {
      this.disposeCurrent();
    }
    this.context = next;
    this.revision += 1;
    return this.context !== undefined;
  }

  clear(): void {
    this.disposeCurrent();
    this.context = undefined;
    this.revision += 1;
  }
}

// Ability and existing entry component import this SAME instance.
export const verificationSession: VerificationSession = new VerificationSession();
