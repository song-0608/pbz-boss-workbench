#include "PBZLab.h"
#include "Animation/AnimInstanceProxy.h"
#include "Animation/AnimSequence.h"
#include "Animation/AnimNodeBase.h"
#include "Animation/AnimationPoseData.h"
#include "AnimationRuntime.h"
#include "GameFramework/CharacterMovementComponent.h"

// Snapshot UObject references on the game thread. Evaluation reads only this
// snapshot and native sequence data; no actor search or file I/O in evaluation.
struct FPBZLabAnimProxy : public FAnimInstanceProxy
{
    using FAnimInstanceProxy::FAnimInstanceProxy;
    UAnimSequence* Idle = nullptr;
    UAnimSequence* Walk = nullptr;
    UAnimSequence* Action = nullptr;
    float IdleTime = 0, WalkTime = 0, ActionTime = 0;
    float MoveAlpha = 0, ActionAlpha = 0, Rate = 1;
    int32 Serial = INDEX_NONE;
    virtual void PreUpdate(UAnimInstance* Instance, float Dt) override
    {
        FAnimInstanceProxy::PreUpdate(Instance, Dt);
        const auto* Character = Cast<APBZLabCharacter>(Instance->TryGetPawnOwner());
        if (!Character) return;
        Idle = Character->IdleClip; Walk = Character->WalkClip;
        const float Speed = Character->GetVelocity().Size2D();
        MoveAlpha = FMath::FInterpTo(MoveAlpha, Speed > 5 ? 1.f : 0.f, Dt, 12);
        Rate = FMath::Clamp(Speed / FMath::Max(1.f, Character->GetCharacterMovement()->MaxWalkSpeed), .75f, 1.6f);
        IdleTime = Idle ? FMath::Fmod(IdleTime + Dt, FMath::Max(.001f, Idle->GetPlayLength())) : 0;
        WalkTime = Walk ? FMath::Fmod(WalkTime + Dt * Rate, FMath::Max(.001f, Walk->GetPlayLength())) : 0;
        if (Character->ActionClip)
        {
            Action = Character->ActionClip;
            ActionTime = Character->ActionElapsed;
            if (Serial != Character->ActionSerial) { Serial = Character->ActionSerial; ActionTime = 0; }
        }
        ActionAlpha = FMath::FInterpTo(ActionAlpha, Character->ActionClip ? 1.f : 0.f, Dt, 18);
        if (ActionAlpha < .001f && !Character->ActionClip) Action = nullptr;
    }
    static void Sample(UAnimSequence* Clip, float Time, FPoseContext& Output)
    {
        Output.ResetToRefPose();
        if (Clip)
        {
            FAnimationPoseData Data(Output);
            Clip->GetAnimationPose(Data, FAnimExtractContext(FMath::Clamp(Time, 0.f, Clip->GetPlayLength()), false));
        }
    }
    virtual bool Evaluate(FPoseContext& Output) override
    {
        Sample(Idle, IdleTime, Output);
        FAnimationPoseData OutputData(Output);
        if (Walk && MoveAlpha > .001f)
        {
            FPoseContext Movement(Output);
            Sample(Walk, WalkTime, Movement);
            FAnimationPoseData MovementData(Movement);
            FAnimationRuntime::BlendTwoPosesTogetherInPlace(OutputData, MovementData, 1 - MoveAlpha);
        }
        if (Action && ActionAlpha > .001f)
        {
            FPoseContext Skill(Output);
            Sample(Action, ActionTime, Skill);
            FAnimationPoseData SkillData(Skill);
            FAnimationRuntime::BlendTwoPosesTogetherInPlace(OutputData, SkillData, 1 - ActionAlpha);
        }
        return true;
    }
};

FAnimInstanceProxy* UPBZLabAnimInstance::CreateAnimInstanceProxy() { return new FPBZLabAnimProxy(this); }
void UPBZLabAnimInstance::DestroyAnimInstanceProxy(FAnimInstanceProxy* Proxy) { delete Proxy; }
