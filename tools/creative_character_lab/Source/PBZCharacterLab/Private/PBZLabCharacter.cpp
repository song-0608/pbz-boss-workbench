#include "PBZLab.h"
#include "Animation/AnimSequence.h"
#include "Camera/CameraComponent.h"
#include "Components/CapsuleComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/AssetManager.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/StreamableManager.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/SpringArmComponent.h"
#include "Kismet/GameplayStatics.h"

APBZLabCharacter::APBZLabCharacter()
{
    PrimaryActorTick.bCanEverTick = true;
    bUseControllerRotationYaw = false;
    GetCapsuleComponent()->InitCapsuleSize(42, 96);
    auto* Move = GetCharacterMovement();
    Move->bOrientRotationToMovement = true;
    Move->RotationRate = FRotator(0, 540, 0);
    Move->MaxWalkSpeed = 480;
    Move->MaxAcceleration = 3200;
    Move->BrakingDecelerationWalking = 2400;
    CameraBoom = CreateDefaultSubobject<USpringArmComponent>(TEXT("CameraBoom"));
    CameraBoom->SetupAttachment(GetRootComponent());
    CameraBoom->TargetArmLength = 480;
    CameraBoom->bUsePawnControlRotation = true;
    CameraBoom->bEnableCameraLag = false;
    CameraBoom->bEnableCameraRotationLag = false;
    CameraBoom->SocketOffset = FVector(0, 45, 65);
    Camera = CreateDefaultSubobject<UCameraComponent>(TEXT("Camera"));
    Camera->SetupAttachment(CameraBoom, USpringArmComponent::SocketName);
    GetMesh()->SetCollisionEnabled(ECollisionEnabled::NoCollision);
    GetMesh()->VisibilityBasedAnimTickOption = EVisibilityBasedAnimTickOption::AlwaysTickPoseAndRefreshBones;
}

void APBZLabCharacter::BeginPlay()
{
    Super::BeginPlay();
    SelectRole(0);
}

bool APBZLabCharacter::SelectRole(int32 Index)
{
    if (!Catalog || !Catalog->Roles.IsValidIndex(Index)) return false;
    const FPBZLabRole& RoleSpec = Catalog->Roles[Index];
    if (RoleSpec.Mesh.IsNull() || (!RoleSpec.MeshPreviewOnly && (RoleSpec.Idle.IsNull() || RoleSpec.Walk.IsNull()))) return false;
    const uint64 Serial = ++LoadSerial;
    if (LoadHandle) LoadHandle->CancelHandle();
    Loading = true;
    Status = FText::Format(FText::FromString(TEXT("正在准备 {0}")), RoleSpec.Name);
    TArray<FSoftObjectPath> Paths {RoleSpec.Mesh.ToSoftObjectPath()};
    if (!RoleSpec.MeshPreviewOnly)
    {
        Paths.AddUnique(RoleSpec.Idle.ToSoftObjectPath());
        Paths.AddUnique(RoleSpec.Walk.ToSoftObjectPath());
    }
    for (const auto& Action : RoleSpec.Actions) if (!Action.Animation.IsNull()) Paths.AddUnique(Action.Animation.ToSoftObjectPath());
    LoadHandle = UAssetManager::GetStreamableManager().RequestAsyncLoad(Paths,
        FStreamableDelegate::CreateWeakLambda(this, [this, Index, Serial]() { FinishLoad(Index, Serial); }));
    if (!LoadHandle) { Loading = false; Status = FText::FromString(TEXT("角色加载未开始")); return false; }
    return true;
}

void APBZLabCharacter::FinishLoad(int32 Index, uint64 Serial)
{
    if (Serial != LoadSerial || !Catalog || !Catalog->Roles.IsValidIndex(Index)) return;
    const FPBZLabRole& RoleSpec = Catalog->Roles[Index];
    Loading = false;
    if (!RoleSpec.Mesh.Get() || (!RoleSpec.MeshPreviewOnly && (!RoleSpec.Idle.Get() || !RoleSpec.Walk.Get())))
    { Status = FText::FromString(TEXT("资源加载失败，保留当前角色")); return; }
    for (const auto& Action : RoleSpec.Actions)
        if (!Action.Animation.Get())
        { Status = FText::FromString(TEXT("动作加载失败，保留当前角色")); return; }
    Current = RoleSpec;
    RoleIndex = Index;
    IdleClip = RoleSpec.Idle.Get(); WalkClip = RoleSpec.Walk.Get(); ActionClip = nullptr;
    LoadedActions.Reset();
    for (const auto& Action : RoleSpec.Actions) LoadedActions.Add(Action.Animation.Get());
    PendingAction = INDEX_NONE; BufferLeft = 0; ActionElapsed = 0; ++ActionSerial;
    Target.Reset(); ManualLookAccumulated = 0;
    GetCharacterMovement()->StopMovementImmediately();
    GetCharacterMovement()->MaxWalkSpeed = FMath::Clamp(RoleSpec.Speed, 150.f, 900.f);
    GetCharacterMovement()->RotationRate = FRotator(0, FMath::Clamp(RoleSpec.TurnRate, 90.f, 900.f), 0);
    GetCharacterMovement()->bOrientRotationToMovement = true;
    const FBoxSphereBounds Bounds = RoleSpec.Mesh.Get()->GetBounds();
    const float HalfHeight = FMath::Clamp(float(Bounds.BoxExtent.Z) * .94f, 96.f, 260.f);
    const float PreviousHeight = GetCapsuleComponent()->GetUnscaledCapsuleHalfHeight();
    GetCapsuleComponent()->SetCapsuleSize(FMath::Clamp(float(Bounds.BoxExtent.X) * .3f, 35.f, 80.f), HalfHeight);
    // Keep the capsule's feet above the same surface when changing size.
    AddActorWorldOffset(FVector(0, 0, HalfHeight - PreviousHeight + 3), false);
    GetMesh()->SetSkeletalMeshAsset(RoleSpec.Mesh.Get());
    GetMesh()->SetRelativeLocation(FVector(0, 0, -HalfHeight));
    GetMesh()->SetRelativeRotation(FRotator(0, RoleSpec.MeshYaw, 0));
    if (RoleSpec.MeshPreviewOnly)
    {
        GetMesh()->SetAnimInstanceClass(nullptr);
        GetMesh()->SetAnimationMode(EAnimationMode::AnimationSingleNode);
        GetMesh()->SetAnimation(nullptr);
        GetMesh()->SetRelativeLocation(FVector(0, 0, -HalfHeight - Bounds.Origin.Z + Bounds.BoxExtent.Z));
    }
    else
    {
        GetMesh()->SetAnimationMode(EAnimationMode::AnimationBlueprint);
        GetMesh()->SetAnimInstanceClass(UPBZLabAnimInstance::StaticClass());
    }
    CameraBoom->TargetArmLength = FMath::Clamp(HalfHeight * 4.6f, 440.f, 1100.f);
    CameraBoom->SocketOffset.Z = HalfHeight * .55f;
    Status = RoleSpec.MeshPreviewOnly
        ? FText::Format(FText::FromString(TEXT("{0} · 模型操控预览")), RoleSpec.Name)
        : FText::Format(FText::FromString(TEXT("{0} · {1} 个动作")), RoleSpec.Name, FText::AsNumber(LoadedActions.Num()));
}

float APBZLabCharacter::GetActionRemaining() const
{
    return ActionClip ? FMath::Max(0.f, ActionClip->GetPlayLength() - ActionElapsed) : 0;
}

bool APBZLabCharacter::StartAction(int32 Slot)
{
    if (!LoadedActions.IsValidIndex(Slot) || !LoadedActions[Slot]) return false;
    ActionClip = LoadedActions[Slot]; ActionElapsed = 0; ++ActionSerial;
    PendingAction = INDEX_NONE; BufferLeft = 0;
    Status = FText::Format(FText::FromString(TEXT("{0} · {1}")), Current.Name, Current.Actions[Slot].Name);
    return true;
}

bool APBZLabCharacter::PlayAction(int32 Slot)
{
    if (Loading || !LoadedActions.IsValidIndex(Slot) || !LoadedActions[Slot]) return false;
    if (!ActionClip) return StartAction(Slot);
    // Only a bounded final-window buffer; no permanent action latch or cooldown counter.
    const float Window = FMath::Clamp(Current.BufferSeconds, 0.f, .25f);
    if (GetActionRemaining() <= Window && Window > 0)
    { PendingAction = Slot; BufferLeft = Window; return true; }
    return false;
}

void APBZLabCharacter::Tick(float DeltaSeconds)
{
    Super::Tick(DeltaSeconds);
    auto* PC = Cast<APBZLabController>(GetController());
    if (ActionClip)
    {
        ActionElapsed += DeltaSeconds;
        if (ActionElapsed >= ActionClip->GetPlayLength())
        {
            ActionClip = nullptr;
            const int32 Next = PendingAction;
            if (Next != INDEX_NONE && BufferLeft > 0) StartAction(Next);
            else { PendingAction = INDEX_NONE; Status = Current.Name; }
        }
    }
    BufferLeft = FMath::Max(0.f, BufferLeft - DeltaSeconds);
    ManualLookQuietTime += DeltaSeconds;
    if (ManualLookQuietTime > .15f) ManualLookAccumulated = 0;
    if (!PC || PC->IsSelectorOpen() || Loading) return;
    float Forward = float(PC->IsInputKeyDown(EKeys::W)) - float(PC->IsInputKeyDown(EKeys::S));
    float Right = float(PC->IsInputKeyDown(EKeys::D)) - float(PC->IsInputKeyDown(EKeys::A));
    const FVector2D Input = FVector2D(Forward, Right).GetClampedToMaxSize(1);
    const FRotator Heading(0, PC->GetControlRotation().Yaw, 0);
    AddMovementInput(Heading.Vector(), Input.X);
    AddMovementInput(FRotationMatrix(Heading).GetUnitAxis(EAxis::Y), Input.Y);
    if (Target.IsValid())
    {
        FVector Aim = Target->GetActorLocation() - GetActorLocation();
        const FRotator Look = Aim.Rotation();
        PC->SetControlRotation(FMath::RInterpTo(PC->GetControlRotation(), Look, DeltaSeconds, 10));
        GetCharacterMovement()->bOrientRotationToMovement = false;
        SetActorRotation(FMath::RInterpConstantTo(GetActorRotation(), FRotator(0, Look.Yaw, 0), DeltaSeconds, Current.TurnRate));
    }
    else GetCharacterMovement()->bOrientRotationToMovement = true;
}

void APBZLabCharacter::Look(float Yaw, float Pitch)
{
    auto* PC = Cast<APBZLabController>(GetController());
    if (!PC || PC->IsSelectorOpen()) return;
    // Axis bindings also tick at zero. They must not reset the quiet interval
    // or isolated mouse nudges would accumulate into an unexpected unlock.
    if (FMath::IsNearlyZero(Yaw) && FMath::IsNearlyZero(Pitch)) return;
    const float Scale = FMath::Clamp(Current.MouseScale, .05f, 1.f);
    const float Limit = FMath::Clamp(Current.LookStepDegrees, 10.f, 45.f);
    const float YawStep = FMath::Clamp(Yaw * Scale, -Limit, Limit);
    const float PitchStep = FMath::Clamp(Pitch * Scale, -Limit, Limit);
    ManualLookQuietTime = 0;
    ManualLookAccumulated += FMath::Abs(YawStep) + FMath::Abs(PitchStep);
    if (ManualLookAccumulated >= Current.UnlockDegrees) Target.Reset();
    FRotator Rotation = PC->GetControlRotation();
    Rotation.Yaw += YawStep;
    Rotation.Pitch = FMath::Clamp(FRotator::NormalizeAxis(Rotation.Pitch) - PitchStep, -70.f, 70.f);
    Rotation.Roll = 0;
    PC->SetControlRotation(Rotation);
}

void APBZLabCharacter::ToggleLock()
{
    if (Target.IsValid()) { Target.Reset(); return; }
    if (!GetController()) return;
    TArray<AActor*> Candidates;
    UGameplayStatics::GetAllActorsWithTag(this, TEXT("PBZLabTarget"), Candidates);
    float Best = TNumericLimits<float>::Max();
    const FVector View = GetController()->GetControlRotation().Vector();
    for (AActor* Actor : Candidates)
    {
        const FVector Offset = Actor->GetActorLocation() - GetActorLocation();
        const float Distance = Offset.Size();
        const float Dot = FVector::DotProduct(Offset.GetSafeNormal(), View);
        if (Distance > 3000 || Dot < .2f) continue;
        const float Score = Distance * (2.f - Dot);
        if (Score < Best) { Best = Score; Target = Actor; }
    }
    ManualLookAccumulated = 0;
}

void APBZLabCharacter::EndPlay(const EEndPlayReason::Type Reason)
{
    ++LoadSerial;
    if (LoadHandle) { LoadHandle->CancelHandle(); LoadHandle.Reset(); }
    Target.Reset();
    Super::EndPlay(Reason);
}
